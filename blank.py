import json
import requests
import time
from datetime import datetime

def check_m3u8_link(url, timeout=10):
    """Check if an m3u8 link is working"""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return response.status_code == 200
    except:
        return False

def fetch_iptv_org_streams():
    """Fetch streams from iptv-org database"""
    print("Fetching fresh streams from iptv-org...")
    
    # Main iptv-org streams JSON
    url = "https://iptv-org.github.io/api/streams.json"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        streams = response.json()
        print(f"Fetched {len(streams)} streams from iptv-org")
        return streams
    except Exception as e:
        print(f"Error fetching iptv-org streams: {e}")
        return []

def find_replacement_stream(channel_name, iptv_streams):
    """Find a replacement stream for a dead channel"""
    channel_name_upper = channel_name.upper()
    
    # Common channel name mappings
    channel_mappings = {
        'FOX NEWS': ['FOX NEWS', 'FOXNEWS'],
        'CBSN': ['CBS NEWS', 'CBSN'],
        'ABC NEWS': ['ABC NEWS', 'ABCNEWS'],
        'CNN': ['CNN'],
        'OANN': ['OAN', 'ONE AMERICA NEWS'],
        'NEWSMAX TV': ['NEWSMAX'],
        'MSNBC': ['MSNBC'],
        'BBC NEWS': ['BBC', 'BBC NEWS'],
        'TBN': ['TBN', 'TRINITY'],
        'TCM': ['TCM', 'TURNER CLASSIC'],
        'AMC': ['AMC'],
        'TNT': ['TNT'],
        'TBS': ['TBS'],
        'CARTOON NETWORK': ['CARTOON NETWORK', 'CN'],
        'NICKTOONS': ['NICKTOONS', 'NICKELODEON'],
        'DISNEY CHANNEL': ['DISNEY CHANNEL', 'DISNEY'],
        'ESPN': ['ESPN'],
        'ESPN2': ['ESPN2', 'ESPN 2'],
        'FS1': ['FOX SPORTS 1', 'FS1'],
        'HBO': ['HBO'],
        'CINEMAX': ['CINEMAX'],
        'STADIUM': ['STADIUM']
    }
    
    # Find matching channel names
    search_terms = []
    for key, values in channel_mappings.items():
        if any(term in channel_name_upper for term in values):
            search_terms.extend(values)
            break
    
    if not search_terms:
        search_terms = [channel_name_upper]
    
    # Search through iptv-org streams
    for stream in iptv_streams:
        stream_name = stream.get('name', '').upper()
        
        for term in search_terms:
            if term in stream_name:
                url = stream.get('url', '')
                if url and url.endswith('.m3u8'):
                    print(f"  Found potential replacement: {stream.get('name')} - {url}")
                    return url
    
    return None

def update_advancefeed():
    """Main function to update dead links in advancefeed.json"""
    print("Starting IPTV Link Fixer...")
    print(f"Current time: {datetime.now()}")
    
    # Load the advancefeed.json file
    try:
        with open('advancefeed.json', 'r') as f:
            feed_data = json.load(f)
    except FileNotFoundError:
        print("Error: advancefeed.json not found!")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing advancefeed.json: {e}")
        return
    
    # Fetch iptv-org streams
    iptv_streams = fetch_iptv_org_streams()
    
    if not iptv_streams:
        print("No streams fetched from iptv-org. Exiting.")
        return
    
    # Track changes
    updated_count = 0
    checked_count = 0
    
    # Process each video in shortFormVideos
    if 'shortFormVideos' in feed_data:
        for video in feed_data['shortFormVideos']:
            checked_count += 1
            
            channel_title = video.get('title', 'Unknown')
            channel_id = video.get('id', 'Unknown')
            
            print(f"\n[{checked_count}] Checking: {channel_title} ({channel_id})")
            
            # Get video content
            content = video.get('content', {})
            videos = content.get('videos', [])
            
            if not videos:
                print("  No video URLs found")
                continue
            
            # Check first video URL
            video_obj = videos[0]
            current_url = video_obj.get('url', '')
            
            if not current_url:
                print("  No URL found")
                continue
            
            print(f"  Current URL: {current_url}")
            
            # Check if the link is working
            is_working = check_m3u8_link(current_url)
            
            if is_working:
                print("  ✓ Link is working")
                continue
            
            print("  ✗ Link is dead, searching for replacement...")
            
            # Find replacement
            new_url = find_replacement_stream(channel_title, iptv_streams)
            
            if new_url:
                # Verify the new URL works
                if check_m3u8_link(new_url):
                    video_obj['url'] = new_url
                    updated_count += 1
                    print(f"  ✓ Updated to: {new_url}")
                else:
                    print(f"  ✗ Replacement URL also dead: {new_url}")
            else:
                print("  ✗ No replacement found")
            
            # Small delay to avoid rate limiting
            time.sleep(0.5)
    
    # Save updated feed
    if updated_count > 0:
        feed_data['lastUpdated'] = datetime.now().isoformat()
        
        with open('advancefeed.json', 'w') as f:
            json.dump(feed_data, f, indent=2)
        
        print(f"\n{'='*60}")
        print(f"✓ Update complete!")
        print(f"  Channels checked: {checked_count}")
        print(f"  Channels updated: {updated_count}")
        print(f"  Last updated: {feed_data['lastUpdated']}")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print(f"No updates needed. All {checked_count} channels are working.")
        print(f"{'='*60}")

if __name__ == "__main__":
    update_advancefeed()
