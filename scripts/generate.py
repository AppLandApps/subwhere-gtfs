import requests
import zipfile
import csv
import json
import io
import os
from datetime import datetime, timezone
from collections import defaultdict

TRAFIKLAB_KEY = os.environ['TRAFIKLAB_KEY']
GTFS_URL = f'https://opendata.samtrafiken.se/gtfs-sweden/sweden.zip?key={TRAFIKLAB_KEY}'

TBANA_ROUTES = {
    '9011001001000000': 10,
    '9011001001100000': 11,
    '9011001001300000': 13,
    '9011001001400000': 14,
    '9011001001700000': 17,
    '9011001001800000': 18,
    '9011001001900000': 19,
}

def main():
    os.makedirs('data', exist_ok=True)

    print('Downloading GTFS Sweden...')
    r = requests.get(GTFS_URL, timeout=300)
    r.raise_for_status()
    print(f'Downloaded {len(r.content) / 1024 / 1024:.1f} MB')

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        print('Files in zip:', z.namelist())

        # --- trips.txt (T-bana only) ---
        print('Processing trips.txt...')
        tbana_trip_ids = set()
        trips_rows = []
        with z.open('trips.txt') as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'))
            fieldnames = reader.fieldnames
            for row in reader:
                if row['route_id'] in TBANA_ROUTES:
                    tbana_trip_ids.add(row['trip_id'])
                    trips_rows.append(row)

        with open('data/trips.txt', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(trips_rows)
        print(f'trips.txt: {len(trips_rows)} T-bana trips')

        # Build direction and line lookups
        trip_direction = {r['trip_id']: r['direction_id'] for r in trips_rows}
        trip_line = {r['trip_id']: TBANA_ROUTES[r['route_id']] for r in trips_rows}

        # --- stop_times.txt → tbana_stop_times.csv ---
        print('Processing stop_times.txt (this takes a while)...')
        stop_times_rows = []
        stop_ids_used = set()

        with z.open('stop_times.txt') as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'))
            for row in reader:
                if row['trip_id'] in tbana_trip_ids:
                    stop_ids_used.add(row['stop_id'])
                    stop_times_rows.append({
                        'trip_id': row['trip_id'],
                        'departure_time': row['departure_time'],
                        'shape_dist_traveled': row.get('shape_dist_traveled', '0'),
                        'stop_id': row['stop_id'],
                        'direction_id': trip_direction.get(row['trip_id'], '0')
                    })

        with open('data/tbana_stop_times.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['trip_id', 'departure_time', 'shape_dist_traveled', 'stop_id', 'direction_id'])
            writer.writeheader()
            writer.writerows(stop_times_rows)
        print(f'tbana_stop_times.csv: {len(stop_times_rows)} rows')

        # --- stops.txt → tbana_stop_names.json and tbana_stations.json ---
        print('Processing stops.txt...')
        stop_names = {}
        stop_coords_all = {}
        stop_names_all = {}

        with z.open('stops.txt') as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'))
            for row in reader:
                sid = row['stop_id']
                name = row['stop_name']
                stop_names_all[sid] = name
                try:
                    stop_coords_all[sid] = (float(row['stop_lat']), float(row['stop_lon']))
                except:
                    pass
                if sid in stop_ids_used:
                    stop_names[sid] = name

        with open('data/tbana_stop_names.json', 'w', encoding='utf-8') as f:
            json.dump(stop_names, f, ensure_ascii=False, indent=2)
        print(f'tbana_stop_names.json: {len(stop_names)} stops')

        # --- tbana_stations.json ---
        print('Processing tbana_stations.json...')
        stop_trip_counts = defaultdict(int)
        stop_dist_map = {}

        with z.open('stop_times.txt') as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'))
            for row in reader:
                tid = row['trip_id']
                if tid not in trip_line:
                    continue
                sid = row['stop_id']
                if sid not in stop_names_all:
                    continue
                line = trip_line[tid]
                direction = int(trip_direction.get(tid, 0))
                key = (line, direction, sid)
                stop_trip_counts[key] += 1
                if key not in stop_dist_map:
                    dist_str = row.get('shape_dist_traveled', '').strip()
                    try:
                        stop_dist_map[key] = float(dist_str) if dist_str else 999999.0
                    except:
                        stop_dist_map[key] = 999999.0

        best_stops = {}
        for (line, direction, sid), count in stop_trip_counts.items():
            name = stop_names_all[sid]
            name_key = (line, direction, name)
            if name_key not in best_stops or count > best_stops[name_key][1]:
                best_stops[name_key] = (sid, count)

        stations_result = []
        for (line, direction, name), (sid, count) in best_stops.items():
            coords = stop_coords_all.get(sid, (0, 0))
            dist = stop_dist_map.get((line, direction, sid), 999999.0)
            stations_result.append({
                'line': line,
                'direction': direction,
                'stop_id': sid,
                'name': name,
                'lat': coords[0],
                'lon': coords[1],
                'shape_dist_traveled': dist
            })

        stations_result = sorted(
            stations_result,
            key=lambda x: (x['line'], x['direction'], x['shape_dist_traveled'])
        )

        with open('data/tbana_stations.json', 'w', encoding='utf-8') as f:
            json.dump(stations_result, f, ensure_ascii=False, indent=2)
        print(f'tbana_stations.json: {len(stations_result)} stations')

    # --- version.json ---
    version = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'trips_count': len(trips_rows),
        'stop_times_count': len(stop_times_rows),
        'stop_names_count': len(stop_names),
        'stations_count': len(stations_result)
    }
    with open('data/version.json', 'w') as f:
        json.dump(version, f, indent=2)
    print(f'version.json written: {version}')
    print('Done!')

if __name__ == '__main__':
    main()
