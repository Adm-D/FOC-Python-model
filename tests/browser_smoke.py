"""End-to-end UI check against a running server; requires Playwright separately.

python tests/browser_smoke.py
CHROMIUM_PATH=/usr/bin/chromium python tests/browser_smoke.py
"""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'outputs'
OUT.mkdir(exist_ok=True)


def ready(page):
    page.wait_for_function("document.querySelector('#run-status').textContent.includes('ЗАВЕРШЁН') && !document.querySelector('#run').disabled", timeout=90000)
    assert page.locator('#error').is_hidden(), page.locator('#error').inner_text()


def main():
    with sync_playwright() as p:
        executable = os.getenv('CHROMIUM_PATH')
        browser = p.chromium.launch(executable_path=executable, headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':1440,'height':1050}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('http://127.0.0.1:8000',wait_until='networkidle')
        ready(page)
        assert page.locator('#signal-count').inner_text()=='54 каналов'
        assert page.locator('#metric-speed').inner_text().replace('\xa0','').replace('\u202f','')=='16000'
        assert page.locator('#mini-speed .scatterlayer .js-line').count()==2
        # Detect global SVG styles accidentally shrinking Plotly's actual surface.
        assert page.locator('#mini-speed .main-svg').first.bounding_box()['width']>250
        page.screenshot(path=str(OUT/'dashboard.png'),full_page=True)

        page.locator('[data-graph=gates]').click()
        page.wait_for_function("document.querySelector('#scope-resolution').textContent.includes('полная временная сетка')")
        assert page.locator('#scope-plot .scatterlayer .js-line').count()==6
        page.screenshot(path=str(OUT/'switching-scope.png'))
        page.locator('[data-range=all]').click()
        page.wait_for_function("document.querySelector('#scope-resolution').textContent.includes('обзор')")
        page.locator('[data-range="0.0001"]').click()
        page.wait_for_function("document.querySelector('#scope-resolution').textContent.includes('полная временная сетка')")
        with page.expect_download() as png:
            page.locator('#save-png').click()
        png.value.save_as(OUT/'scope.png')
        assert (OUT/'scope.png').stat().st_size>10000
        page.locator('#graph-dialog .close-dialog').click()

        page.locator('[data-tab=transforms]').click()
        page.locator('#mini-inverse_clarke .scatterlayer .js-line').first.wait_for()
        assert page.locator('.chart-card').count()==6
        page.locator('[data-tab=energy]').click()
        page.locator('#mini-rotor .scatterlayer .js-line').first.wait_for()
        assert page.locator('#mini-rotor .scatterlayer .js-line').count()==2
        page.locator('[data-tab=overview]').click()
        page.locator('#mini-emf .scatterlayer .js-line').first.wait_for()

        page.locator('#preset').select_option('6V')
        assert page.locator('[data-key=resistance]').input_value()=='11.4'
        assert page.locator('[data-key=ld]').input_value()=='142.5'
        page.locator('#run').click()
        ready(page)
        assert '6,00' in page.locator('#bus-label').inner_text()
        page.locator('[data-scenario=reverse]').click()
        page.locator('#run').click()
        ready(page)
        speed=page.locator('#metric-speed').inner_text().replace('\xa0','').replace('\u202f','')
        assert abs(float(speed)-8000)<100

        page.locator('#export-top').click()
        with page.expect_download() as saved:
            page.locator('#export-json').click()
        saved.value.save_as(OUT/'ui-config.json')
        exported=json.loads((OUT/'ui-config.json').read_text())
        assert exported['motor']['vdc']==6
        assert exported['speed'][1]['value']==-12000
        page.locator('#export-dialog .close-dialog').click()
        page.locator('#preset').select_option('3V')
        page.locator('#import-file').set_input_files(str(OUT/'ui-config.json'))
        page.wait_for_function("document.querySelector('[data-key=resistance]').value === '11.4'")

        # Bad inputs must show a useful validation error, preserving previous data.
        page.locator('#duration').fill('1')
        page.locator('#run').click()
        page.locator('#error').wait_for(state='visible')
        assert 'раньше конца' in page.locator('#error').inner_text()
        page.locator('#duration').fill('120')
        page.locator('#theory-top').click()
        page.wait_for_function("document.querySelector('#model-docs').textContent.includes('Pillay')")
        page.locator('#docs-dialog .close-dialog').click()
        assert not errors, errors

        mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1,is_mobile=True,has_touch=True)
        mobile.on('pageerror',lambda e:errors.append(str(e)))
        mobile.goto('http://127.0.0.1:8000',wait_until='networkidle')
        ready(mobile)
        assert not mobile.evaluate('document.documentElement.scrollWidth > innerWidth')
        mobile.screenshot(path=str(OUT/'mobile.png'),full_page=True)
        mobile.locator('[data-graph=currents]').count()  # overview opened via chart button
        mobile.locator('#mini-currents').locator('..').get_by_role('button').click()
        mobile.locator('#scope-plot .scatterlayer .js-line').first.wait_for()
        assert mobile.locator('#scope-plot .main-svg').first.bounding_box()['width']>250
        mobile.screenshot(path=str(OUT/'mobile-scope.png'))
        assert not errors, errors
        browser.close()
        print('Browser checks passed: default run, visible plots, PWM detail/zoom, PNG, transforms, energy, 6 V, reversal, JSON export/import, validation, docs, mobile.')


if __name__=='__main__':
    main()
