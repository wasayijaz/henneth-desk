"""Offline regression checks for DPS ticker identity versus display badges."""
from unittest.mock import patch
from types import SimpleNamespace

import psx_data as data
from update_universe import _intake, _merge_source


def row(symbol, badge="", order=None):
    cell = (f'<td data-order="{order or symbol}"><a href="/company/{symbol}">'
            f'<strong>{symbol}</strong></a>{badge}</td>')
    return '<tr>' + cell + ''.join(f'<td>{v}</td>' for v in
        ['Example &amp; Company', '1', '2', '1', '1', '3']) + '</tr>'


def main():
    badge = '<div class="tag tag--skim tag--def">NC</div>'
    html = row('HASCOL', badge) + row('EPCLPS') + row('NCML') + row('REALNC')
    with patch.object(data, '_get', return_value=SimpleNamespace(text=html)):
        records = data.index_constituents('ALLSHR')
    assert [r['symbol'] for r in records] == ['HASCOL', 'EPCLPS', 'NCML', 'REALNC']
    assert records[0]['source_badges'] == ['NC']
    assert records[0]['name'] == 'Example & Company'
    assert 'source_badges' not in records[1]
    record = _intake(records[0], ['ALLSHR'], 'listed')
    assert record['symbol'] == 'HASCOL' and record['source_badges'] == ['NC']
    other = {'symbol': 'HASCOL'}
    _merge_source(other, record)
    assert other['source_badges'] == ['NC']

    for invalid in [row('HASCOL', order='ANOTHER'), row('HASCOL') * 2,
                    row('HASCOL').replace('/company/HASCOL', '/unrelated/HASCOL')]:
        with patch.object(data, '_get', return_value=SimpleNamespace(text=invalid)):
            try:
                data.index_constituents('ALLSHR')
            except ValueError:
                pass
            else:
                raise AssertionError('ambiguous source identity accepted')

    headers = ['symbol', 'sector', 'indices', 'ldcp', 'open', 'high', 'low',
               'close', 'change', 'change_p', 'volume']
    market = ''.join(f'<th data-name="{h}"></th>' for h in headers)
    market += ('<tr><td data-order="HASCOL"><a href="/company/HASCOL">HASCOL</a>'
               + badge + '</td>' + ''.join(f'<td>{v}</td>' for v in
               ['0821', 'ALLSHR', '10', '10', '11', '9', '10.5', '0.5', '5%', '123']) + '</tr>')
    with patch.object(data, '_get', return_value=SimpleNamespace(text=market)):
        snap = data.market_watch()
    assert set(snap) == {'HASCOL'}
    assert snap['HASCOL']['current'] == 10.5 and snap['HASCOL']['volume'] == 123
    assert snap['HASCOL']['source_badges'] == ['NC']
    with patch.object(data, '_get', return_value=SimpleNamespace(
            text=market.replace('HASCOL', 'MZNPETF').replace('/company/', '/etf/'))):
        assert 'MZNPETF' in data.market_watch()
    assert data.canonical_symbol('EPCLPS') == 'EPCLPS'
    assert data.canonical_symbol('REALNC') == 'REALNC'
    assert data.canonical_symbol('FFCXD') == 'FFC'
    print('security identity checks: PASS (badges, preferences, collisions, market-watch)')


if __name__ == '__main__':
    main()
