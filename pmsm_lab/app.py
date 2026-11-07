"""Local FastAPI application. A single simulation worker bounds memory usage."""
import csv
import io
import json
from pathlib import Path
import threading
from uuid import uuid4

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import SimulationConfig, CATALOG, CATALOG_COMMON, motor_preset
from .signals import SIGNALS, GROUPS
from .simulation import simulate

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title='PMSM // Drive Lab', version='0.1.0')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
results = {}
lock = threading.Lock()


@app.get('/')
def index():
    return FileResponse(ROOT / 'static/index.html')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'model': 'switching-pmsm', 'controller': 'foc'}


@app.get('/api/defaults')
def defaults():
    return dict(config=SimulationConfig().model_dump(),
                presets={n: motor_preset(n).model_dump() for n in CATALOG},
                catalog=CATALOG, common=CATALOG_COMMON, signals=SIGNALS, groups=GROUPS)


@app.get('/api/model')
def model_docs():
    return Response((ROOT / 'docs/MODEL.md').read_text(), media_type='text/plain; charset=utf-8')


@app.get('/api/catalog')
def catalog_pdf():
    return FileResponse(ROOT / 'docs/Cataloge-Page-EN-193.pdf', media_type='application/pdf')


@app.post('/api/simulate')
def run(config: SimulationConfig):
    if not lock.acquire(blocking=False):
        raise HTTPException(409, 'Расчёт уже выполняется. Дождитесь завершения.')
    try:
        result = simulate(config)
        rid = uuid4().hex
        # Only the latest result is retained. Existing downloads hold their own
        # reference; stale IDs fail explicitly instead of returning new data.
        results.clear()
        results[rid] = result
        return dict(id=rid, config=config.model_dump(), metrics=result.metrics, warnings=result.warnings)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        lock.release()


@app.post('/api/validate')
def validate(config: SimulationConfig):
    return config.model_dump()


def get_result(rid):
    if rid not in results:
        raise HTTPException(404, 'Результат не найден или заменён новым расчётом.')
    return results[rid]


@app.get('/api/results/{rid}/signals')
def signals(rid: str, names: str = 'speed_rpm,speed_ref_rpm',
            start: float = Query(0, ge=0, allow_inf_nan=False),
            end: float | None = Query(None, gt=0, allow_inf_nan=False),
            limit: int = Query(2000, ge=100, le=20000)):
    requested = list(dict.fromkeys(names.split(',')))
    if not requested or len(requested) > 16 or any(n not in SIGNALS for n in requested):
        raise HTTPException(422, 'Выберите от 1 до 16 существующих сигналов.')
    if end is not None and end <= start:
        raise HTTPException(422, 'Конец интервала должен быть больше начала.')
    return get_result(rid).window(requested, start, end, limit)


@app.get('/api/results/{rid}/config')
def export_config(rid: str):
    return Response(get_result(rid).config.model_dump_json(indent=2), media_type='application/json',
                    headers={'Content-Disposition': 'attachment; filename="pmsm-config.json"'})


@app.get('/api/results/{rid}/csv')
def export_csv(rid: str):
    result = get_result(rid)
    def rows():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        names = list(SIGNALS)
        writer.writerow(['time_s'] + [f'{n} [{SIGNALS[n]["unit"]}]' for n in names])
        for a in range(0, len(result.time), 2048):
            b = min(a + 2048, len(result.time))
            matrix = np.column_stack([result.time[a:b]] + [result.signals[n][a:b] for n in names])
            writer.writerows(matrix)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
    return StreamingResponse(rows(), media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="pmsm-full-resolution.csv"'})


@app.get('/api/results/{rid}/npz')
def export_npz(rid: str):
    result = get_result(rid)
    b = io.BytesIO()
    np.savez_compressed(b, time=result.time, **result.signals,
                        config_json=result.config.model_dump_json(), metrics_json=json.dumps(result.metrics))
    b.seek(0)
    return StreamingResponse(iter(lambda: b.read(1024*1024), b''), media_type='application/octet-stream',
        headers={'Content-Disposition': 'attachment; filename="pmsm-result.npz"'})
