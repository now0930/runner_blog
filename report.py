"""Readable, data-backed WordPress running reports."""
from html import escape


def _duration(seconds):
    if seconds is None:
        return '—'
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{hours}시간 {minutes}분 {seconds}초' if hours else f'{minutes}분 {seconds}초'


def _pace(distance, duration):
    if not distance or not duration or duration <= 0:
        return '—'
    minutes, seconds = divmod(round(duration * 1000 / distance), 60)
    return f'{minutes}:{seconds:02d}/km'


def _metric(value, unit='', digits=0):
    return f'{value:.{digits}f}{unit}' if value is not None else '자료 없음'


def render_walking_report(stats):
    """Walking posts contain only measured total distance and duration."""
    distance = stats['distance'] / 1000
    duration = _duration(stats['duration'])
    title = f'걷기 기록: {distance:.2f}km · {duration}'
    content = (f'<p>총 거리: {distance:.2f}km</p>\n'
               f'<p>총 시간: {escape(duration)}</p>')
    return title, content


def render_report(stats, analysis, file_name):
    """Render measured stats separately from the model's prose."""
    distance, duration = stats.get('distance'), stats.get('duration')
    splits = stats.get('splits') or []
    speed = distance / duration * 3.6 if distance and duration else None
    headline = [
        ('거리', _metric(distance / 1000 if distance else None, 'km', 2)),
        ('시간', _duration(duration)),
        ('평균 페이스', _pace(distance, duration)),
        ('평균 속도', _metric(speed, 'km/h', 1)),
    ]
    if stats.get('heart_rate_avg') is not None:
        headline += [('평균 심박', _metric(stats['heart_rate_avg'], 'bpm')),
                     ('최대 심박', _metric(stats.get('heart_rate_max'), 'bpm'))]
    if stats.get('cadence_avg') is not None:
        headline += [('평균 케이던스', _metric(stats['cadence_avg'], 'spm')),
                     ('최대 케이던스', _metric(stats.get('cadence_max'), 'spm'))]

    rows = []
    for index in range(0, len(headline), 2):
        rows.append('<tr>' + cells_for(headline[index:index + 2]) + '</tr>')
    html = ['<h2>러닝 기록 한눈에 보기</h2>',
            '<table style="width:100%;border-collapse:collapse"><tbody>', *rows,
            '</tbody></table>']
    if stats.get('date'):
        html.append(f'<p>운동 시각: {escape(stats["date"])} ~ {escape(stats.get("end_date") or "기록 없음")} (한국 시간)</p>')
    weather = (analysis or {}).get('weather')
    if weather:
        html.append(f'<p>날씨: {escape(weather)}</p>')

    if splits:
        html += ['<h2>구간별 기록</h2>',
                 '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse"><thead><tr>',
                 '<th>구간</th><th>거리</th><th>시간</th><th>평균 페이스</th><th>평균 심박</th><th>평균 케이던스</th><th>평균 고도</th>',
                 '</tr></thead><tbody>']
        for split in splits:
            row = [str(split['km']), _metric(split.get('distance', 0) / 1000, 'km', 2),
                   _duration(split.get('duration')),
                   _pace(split.get('distance'), split.get('duration')),
                   _metric(split.get('heart_rate'), 'bpm'),
                   _metric(split.get('cadence'), 'spm'),
                   _metric(split.get('elevation'), 'm', 1)]
            shade = '#f3f7fc' if split['km'] % 2 else '#fff'
            html.append(f'<tr style="background:{shade}">' + ''.join(
                f'<td style="padding:8px;border-bottom:1px solid #ddd">{escape(value)}</td>' for value in row) + '</tr>')
        html += ['</tbody></table></div>',
                 '<p><small>구간 경계는 GPS 거리로 보간했습니다. 마지막 행은 남은 거리입니다. 심박·케이던스·고도는 해당 구간의 기록 샘플 평균입니다.</small></p>']

    html += ['<h2>GPX에 기록된 추가 정보</h2>', '<ul>']
    if stats.get('elevation_min') is not None:
        html.append('<li>고도: 최저 ' + _metric(stats['elevation_min'], 'm', 1) +
                    ' · 최고 ' + _metric(stats.get('elevation_max'), 'm', 1) +
                    ' · 시작 ' + _metric(stats.get('elevation_start'), 'm', 1) +
                    ' · 종료 ' + _metric(stats.get('elevation_end'), 'm', 1) + '</li>')
    html.append(f'<li>GPS 기록점: {stats.get("point_count", 0):,}개</li>')
    html += ['</ul>', '<h2>기록 해석</h2>']
    summary = (analysis or {}).get('summary', '').strip()
    if summary:
        html.extend(f'<p>{escape(line.strip())}</p>' for line in summary.splitlines() if line.strip())

    training = (analysis or {}).get('training')
    if not isinstance(training, list) or not training or not all(isinstance(item, str) and item.strip() for item in training):
        raise ValueError('Model training recommendations are required for the report')
    html += ['<h2>다음 훈련 제안</h2>', '<ol>']
    html.extend(f'<li>{escape(item.strip())}</li>' for item in training)
    html += ['</ol>',
             '<p><small>심박 구간과 훈련 강도는 개인의 최대 심박수·평소 기록·체감 강도가 없어 단정할 수 없습니다. 고도는 GPS 기록값이며 누적 상승량을 뜻하지 않습니다.</small></p>',
             f'<h2>달린 경로</h2><p>[sgpx gpx="/wp-content/uploads/gpx/{escape(file_name, quote=True)}"]</p>']
    return '\n'.join(html)


def cells_for(items):
    return ''.join(f'<td style="padding:12px;border:1px solid #ddd"><strong>{escape(label)}</strong><br>{escape(value)}</td>'
                   for label, value in items)
