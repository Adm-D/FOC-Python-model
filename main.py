#!/usr/bin/env python3
"""Local launcher: python3 main.py. Only the standard library is needed initially."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import venv

from pmsm_lab.cli import build_parser


ROOT = Path(__file__).resolve().parent


def prepare_python() -> Path:
    """Create/reuse an isolated environment beside the application, never globally."""
    if not (3, 11) <= sys.version_info[:2] < (3, 14):
        raise RuntimeError('Для запуска нужен Python 3.11–3.13. Рекомендуется Python 3.12.')
    environment = ROOT / '.venv'
    python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.is_file():
        if environment.exists():
            raise RuntimeError(
                'Папка .venv существует, но интерпретатор в ней не найден. '
                'Переименуйте эту папку и повторите запуск; её файлы сохранены.'
            )
        print('Первый запуск: создаю локальное Python-окружение .venv…', flush=True)
        try:
            venv.EnvBuilder(with_pip=True).create(environment)
        except (OSError, subprocess.CalledProcessError) as error:
            raise RuntimeError(
                'Не удалось создать .venv. Проверьте право записи в папку программы '
                'и наличие модуля venv/ensurepip. В Ubuntu/Debian он устанавливается '
                'пакетом python3-venv. Подробности: ' + str(error)
            ) from error

    # Metadata checks work offline; pip runs only on initial setup or a lock change.
    check = '''
import importlib.metadata
import pathlib
import sys
if not (3, 11) <= sys.version_info[:2] < (3, 14):
    sys.exit(2)
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    name, expected = line.split('==', 1)
    try:
        if importlib.metadata.version(name) != expected:
            sys.exit(1)
    except importlib.metadata.PackageNotFoundError:
        sys.exit(1)
'''
    lockfile = ROOT / 'requirements.lock'
    checked = subprocess.run([str(python), '-c', check, str(lockfile)], check=False)
    if checked.returncode == 2:
        raise RuntimeError('Python в .venv несовместим. Переименуйте .venv и запустите с Python 3.11–3.13.')
    if checked.returncode not in (0, 1):
        raise RuntimeError('Не удалось проверить зависимости в .venv. См. сообщение Python выше.')
    if checked.returncode == 1:
        print('Устанавливаю зависимости в .venv. На этом этапе нужен интернет…', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                        '-r', str(lockfile)], check=True)
    return python


def main() -> int:
    # Help and invalid arguments must not create environments or download packages.
    build_parser().parse_args()
    try:
        python = prepare_python()
        return subprocess.run([str(python), '-m', 'pmsm_lab', *sys.argv[1:]], cwd=ROOT).returncode
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f'Ошибка запуска: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
