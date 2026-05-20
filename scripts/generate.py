import requests
import zipfile
import csv
import json
import io
import os
from datetime import datetime, timezone

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

        # --- stop_times.txt → tbana_stop_times.csv ---
        print('Processing stop_times.txt (this takes a while)...')
        stop_ids_used = set()
        stop_times_rows = []

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
                        'direction_id': next(
                            (r['direction_id'] for r in trips_rows if r['trip_id'] == row['trip_id']),
                            '0'
                        )
                    })

        # Build direction lookup for efficiency
        trip_direction = {r['trip_id']: r['direction_id'] for r in trips_rows}
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

        # --- stops.txt → tbana_stop_names.json ---
        print('Processing stops.txt...')
        stop_names = {}
        with z.open('stops.txt') as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'))
            for row in reader:
                if row['stop_id'] in stop_ids_used:
                    stop_names[row['stop_id']] = row['stop_name']

        with open('data/tbana_stop_names.json', 'w', encoding='utf-8') as f:
            json.dump(stop_names, f, ensure_ascii=False, indent=2)
        print(f'tbana_stop_names.json: {len(stop_names)} stops')

    # --- version.json ---
    version = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'trips_count': len(trips_rows),
        'stop_times_count': len(stop_times_rows),
        'stop_names_count': len(stop_names)
    }
    with open('data/version.json', 'w') as f:
        json.dump(version, f, indent=2)
    print(f'version.json written: {version}')
    print('Done!')

if __name__ == '__main__':
    main()
