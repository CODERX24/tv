import requests
import json
import os

# 1. Fetch fresh data from iptv-org API
print("Fetching fresh streams from iptv-org...")
try:
    streams_data = requests.get("https://iptv-org.github.io/api/streams.json").json()
    # Create a lookup: {'AMC': 'http://link.m3u8'}
    # We check for channel name and channel ID (like AMC.us)
    stream_map = {}
    for s in streams_data:
        if s.get('status') == 'online':
            name_key = s['channel'].split('.')[0].upper()
            stream_map[name_key] = s['url']
except Exception as e:
    print(f"Error fetching API: {e}")
    exit(1)

def is_link_dead(url):
    if not url or not url.startswith('http'): return True
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        return r.status_code >= 400
    except:
        return True

# 2. Load your local advancefeed.json
json_file = 'advancefeed.json'
if not os.path.exists(json_file):
    print(f"Error: {json_file} not found!")
    exit(1)

with open(json_file, 'r') as f:
    data = json.load(f)

# 3. Update the URLs inside the JSON
updated_count = 0
for item in data:
    channel_name = item.get('name', '').upper()
    current_url = item.get('url', '')

    if is_link_dead(current_url):
        print(f"Link dead for {channel_name}. Searching replacement...")
        # Look for a match in our stream_map
        new_url = stream_map.get(channel_name)
        
        if new_url and new_url != current_url:
            item['url'] = new_url
            updated_count += 1
            print(f"✅ Updated {channel_name}")
        else:
            print(f"❌ No online source found for {channel_name}")

# 4. Save the updated JSON back to the file
with open(json_file, 'w') as f:
    json.dump(data, f, indent=4)

print(f"Task finished. Updated {updated_count} links.")
