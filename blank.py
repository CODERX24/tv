import json
import requests
import time
from datetime import datetime
import re

def check_m3u8_link(url, timeout=15):
    """Check if an m3u8 link actually works by downloading and parsing it"""
    try:
        # First, try to get the m3u8 file
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        
        if response.status_code != 200:
            return False
        
        content = response.text
        
        # Check if it's actually an m3u8 file (should contain #EXTM3U)
        if '#EXTM3U' not in content:
            print(f"    Not a valid m3u8 file (missing #EXTM3U header)")
            return False
        
        # Extract actual stream URLs from the m3u8 playlist
        stream_urls = []
        for line in content.split('\n'):
            line = line.strip()
            # Skip comments and empty lines
            if line and not line.startswith('#'):
                # Handle relative URLs
                if line.startswith('http'):
                    stream_urls.append(line)
                else:
                    # Construct absolute URL from relative path
                    base_url = '/'.join(url.split('/')[:-1])
                    stream_urls.append(f"{base_url}/{line}")
        
        if not stream_urls:
            print(f"    No stream URLs found in m3u8 playlist")
            return False
        
        # Test the first stream URL to see if it's reachable
        test_url = stream_urls[0]
        print(f"    Testing actual stream: {test_url[:80]}...")
        
        # Try to fetch a small chunk of the actual stream
        stream_response = requests.get(test_url, timeout=timeout, stream=True, allow_redirects=True)
        
        if stream_response.status_code != 200:
            print(f"    Stream returned status: {stream_response.status_code}")
            return False
        
        # Read a small chunk to verify it's actually streaming data
        chunk = next(stream_response.iter_content(chunk_size=1024), None)
        stream_response.close()
        
        if chunk is None or len(chunk) == 0:
            print(f"    Stream returned no data")
            return False
        
        print(f"    ✓ Stream is working and serving data")
        return True
        
    except requests.exceptions.Timeout:
        print(f"    Timeout while checking stream")
        return False
    except requests.exceptions.ConnectionError:
        print(f"    Connection error")
        return False
    except Exception as e:
        print(f"    Error: {str(e)[:100]}")
        return False

def is_channel_mismatch(channel_title, stream_name, stream_title, url):
    """
    Detect if a stream is a mismatch for the requested channel.
    Returns (is_mismatch, reason, penalty_score)
    """
    channel_upper = channel_title.upper()
    stream_name_upper = stream_name.upper()
    stream_title_upper = stream_title.upper()
    url_lower = url.lower()
    
    # Remove common suffixes for cleaner matching
    channel_clean = channel_upper.replace('(TEMPORARY)', '').replace('GEO-BLOCKED', '').replace('(LATENCY)', '').strip()
    
    # Detect local affiliates and wrong stations
    local_indicators = [
        'LOCAL', 'AFFILIATE', 'KDFW', 'KTVU', 'WTTG', 'WNYW', 'KTTV',
        'FOX 2', 'FOX 4', 'FOX 5', 'FOX 7', 'FOX 9', 'FOX 10', 'FOX 11', 'FOX 13',
        'FOX 25', 'FOX 26', 'FOX 29', 'FOX 32', 'FOX 35', 'FOX 46',
        'WTXF', 'WFXT', 'WJBK', 'WTVT', 'WAGA', 'KRIV',
        'WASHINGTON', 'NEW YORK', 'LOS ANGELES', 'CHICAGO', 'DALLAS', 'ATLANTA',
        'DETROIT', 'MIAMI', 'BOSTON', 'PHOENIX', 'SEATTLE', 'HOUSTON'
    ]
    
    # Check if looking for Fox News specifically
    if 'FOX NEWS' in channel_clean or 'FOXNEWS' in channel_clean:
        # Reject local Fox stations
        for indicator in local_indicators:
            if indicator in stream_name_upper or indicator in stream_title_upper:
                return (True, 'Local Fox affiliate, not Fox News Channel', -60)
        
        # Reject if it doesn't explicitly say "NEWS" or "FNC"
        if 'NEWS' not in stream_name_upper and 'NEWS' not in stream_title_upper and 'FNC' not in stream_name_upper:
            # But allow if the URL clearly indicates fox news
            if 'foxnews' not in url_lower and 'fox_news' not in url_lower and 'fox-news' not in url_lower:
                return (True, 'Fox channel but not Fox News', -55)
    
    # Define unacceptable mismatches and secondary variants
    mismatch_rules = {
        'FOX NEWS': {
            'avoid': ['FOX BUSINESS', 'FOX SPORTS', 'FOX DEPORTES', 'FOX SOCCER', 'FS1', 'FS2', 'FOX MOVIES', 'FOX LIFE'],
            'penalty_score': -50,
            'reason': 'Wrong Fox network'
        },
        'ESPN': {
            'avoid': ['DEPORTES', 'DEPORTIVAS', 'SPANISH', 'LATINO', 'PLUS', 'ESPN+', 'ESPN2', 'ESPN 2', 'ESPNU', 'ESPN U', 'COLLEGE'],
            'penalty_score': -50,
            'reason': 'Secondary/International ESPN variant'
        },
        'ESPN2': {
            'avoid': ['DEPORTES', 'SPANISH', 'LATINO', 'PLUS'],
            'penalty_score': -50,
            'reason': 'Wrong ESPN variant'
        },
        'AMC': {
            'avoid': ['AMC+', 'PLUS', 'AMCPLUS', 'SUNDANCE', 'IFC', 'SHUDDER', 'ACORN'],
            'penalty_score': -40,
            'reason': 'AMC secondary service, not main channel'
        },
        'HBO': {
            'avoid': ['HBO2', 'HBO 2', 'HBO3', 'HBO 3', 'HBO MAX', 'HBOMAX', 'MAX', 'FAMILY', 'COMEDY', 'ZONE', 'SIGNATURE', 'LATINO'],
            'penalty_score': -40,
            'reason': 'HBO secondary channel, not main HBO'
        },
        'CNN': {
            'avoid': ['CNN INTERNATIONAL', 'CNN ESPAÑOL', 'CNN TURK', 'CNN BRASIL', 'HLN'],
            'penalty_score': -30,
            'reason': 'International CNN variant'
        },
        'MSNBC': {
            'avoid': ['CNBC', 'NBC SPORTS', 'NBC 2', 'NBC 4', 'NBC 5', 'NBC 7', 'WNBC', 'KNBC'],
            'penalty_score': -40,
            'reason': 'Wrong NBC network'
        },
        'CBS NEWS': {
            'avoid': ['CBS SPORTS', 'CBS 2', 'CBS 3', 'CBS 4', 'CBS 5', 'WCBS', 'KCBS', 'LOCAL'],
            'penalty_score': -40,
            'reason': 'Local CBS station, not CBS News'
        },
        'ABC NEWS': {
            'avoid': ['ABC 7', 'ABC 13', 'WABC', 'KABC', 'WLS', 'LOCAL'],
            'penalty_score': -40,
            'reason': 'Local ABC station, not ABC News'
        },
        'DISCOVERY': {
            'avoid': ['DISCOVERY+', 'PLUS', 'ID', 'INVESTIGATION', 'SCIENCE', 'FAMILIA', 'TURBO', 'THEATER'],
            'penalty_score': -30,
            'reason': 'Discovery secondary channel'
        },
        'NATIONAL GEOGRAPHIC': {
            'avoid': ['NAT GEO WILD', 'WILD', 'MUNDO', 'LATIN'],
            'penalty_score': -30,
            'reason': 'Nat Geo secondary channel'
        },
        'CARTOON NETWORK': {
            'avoid': ['BOOMERANG', 'TOONAMI', 'CARTOON NETWORK ARABIC'],
            'penalty_score': -30,
            'reason': 'Wrong Cartoon Network variant'
        },
        'DISNEY CHANNEL': {
            'avoid': ['DISNEY+', 'DISNEY PLUS', 'DISNEY XD', 'DISNEY JR', 'DISNEY JUNIOR'],
            'penalty_score': -35,
            'reason': 'Disney secondary channel'
        },
        'TBS': {
            'avoid': ['TNT', 'TRUTV', 'TCM'],
            'penalty_score': -40,
            'reason': 'Wrong Turner network'
        },
        'TNT': {
            'avoid': ['TBS', 'TRUTV', 'TCM'],
            'penalty_score': -40,
            'reason': 'Wrong Turner network'
        }
    }
    
    # Check against mismatch rules
    for channel_key, rules in mismatch_rules.items():
        if channel_key in channel_clean:
            avoid_terms = rules['avoid']
            
            # Check if any avoid terms are in the stream name or title
            for avoid_term in avoid_terms:
                if avoid_term in stream_name_upper or avoid_term in stream_title_upper or avoid_term in url_lower:
                    return (True, rules['reason'], rules['penalty_score'])
    
    # General secondary channel detection (lighter penalty, as last resort)
    secondary_indicators = [
        'PLUS', '+', '2', '3', 'HD', 'EXTRA', 'XTRA', 'FAMILIA', 'LATINO', 'LATIN', 
        'SPANISH', 'ESPAÑOL', 'ALTERNATIVE', 'ALT'
    ]
    
    # Only apply if it's a clear secondary variant (has the base name + indicator)
    for indicator in secondary_indicators:
        # Check if stream has base channel name plus secondary indicator
        if channel_clean in stream_name_upper and indicator in stream_name_upper:
            # Make sure it's truly a secondary channel (not just "HD" in description)
            if indicator in ['2', '3', 'PLUS', '+', 'EXTRA', 'XTRA']:
                return (True, f'Secondary channel variant ({indicator})', -25)
    
    return (False, None, 0)

def get_stream_quality_score(url, stream_data, channel_title=''):
    """
    Assign a quality score to a stream based on URL patterns and metadata.
    Higher score = better quality
    Includes mismatch penalties for wrong channels
    """
    score = 50  # Base score
    url_lower = url.lower()
    
    # Check for channel mismatches first (can heavily penalize)
    stream_name = stream_data.get('name', '')
    stream_title = stream_data.get('title', '')
    is_mismatch, mismatch_reason, penalty = is_channel_mismatch(
        channel_title, stream_name, stream_title, url
    )
    
    if is_mismatch:
        score += penalty  # Apply penalty (negative number)
        # Store mismatch info in stream_data for logging
        stream_data['_mismatch_reason'] = mismatch_reason
    
    # Country priority (US-based app)
    country = stream_data.get('country', '').upper()
    if country == 'US' or country == 'USA' or country == 'UNITED STATES':
        score += 40  # High bonus for US streams
    elif country == 'UK' or country == 'CA' or country == 'CANADA':
        score += 20  # Medium bonus for English-speaking countries
    elif country == 'INT' or country == 'INTERNATIONAL':
        score += 10  # Small bonus for international feeds
    elif country:  # Any other country
        score += 5
    # No country specified gets no bonus
    
    # Check for resolution indicators in URL (keywords)
    if '2160' in url_lower or '4k' in url_lower or 'uhd' in url_lower:
        score += 40
    elif '1440' in url_lower or '2k' in url_lower:
        score += 35
    elif '1080' in url_lower or 'fhd' in url_lower or '1920' in url_lower:
        score += 30
    elif '900' in url_lower or '720' in url_lower or 'hd' in url_lower or '1280' in url_lower:
        score += 20
    elif '600' in url_lower or '480' in url_lower or 'sd' in url_lower or '640' in url_lower or '854' in url_lower:
        score += 10
    elif '360' in url_lower or '240' in url_lower or '426' in url_lower or '320' in url_lower:
        score -= 10
    
    # Extract resolution from URL patterns like "750x600", "1280x720", etc.
    resolution_pattern = r'(\d{3,4})[x_\-](\d{3,4})'
    matches = re.findall(resolution_pattern, url_lower)
    if matches:
        for width, height in matches:
            width_int = int(width)
            height_int = int(height)
            # Use the larger dimension (could be width or height)
            max_dimension = max(width_int, height_int)
            
            if max_dimension >= 2160:
                score += 40
            elif max_dimension >= 1440:
                score += 35
            elif max_dimension >= 1080:
                score += 30
            elif max_dimension >= 900:
                score += 25
            elif max_dimension >= 720:
                score += 20
            elif max_dimension >= 600:
                score += 15
            elif max_dimension >= 480:
                score += 10
            elif max_dimension >= 360:
                score += 5
            break  # Only use first resolution found
    
    # Check resolution in stream metadata if available
    resolution = stream_data.get('resolution', {})
    if resolution:
        width = resolution.get('width', 0)
        height = resolution.get('height', 0)
        max_dimension = max(width, height)
        
        if max_dimension >= 2160:
            score += 40
        elif max_dimension >= 1440:
            score += 35
        elif max_dimension >= 1080:
            score += 30
        elif max_dimension >= 900:
            score += 25
        elif max_dimension >= 720:
            score += 20
        elif max_dimension >= 600:
            score += 15
        elif max_dimension >= 480:
            score += 10
        elif max_dimension >= 360:
            score += 5
    
    # Prefer certain reliable domains/providers
    reliable_domains = [
        'i.mjh.nz',
        'iptv-org.github.io',
        'livetv.sx',
        'ustv247.tv',
        'moveonjoy.com'
    ]
    
    for domain in reliable_domains:
        if domain in url_lower:
            score += 15
            break
    
    # Penalize certain indicators of lower quality
    if 'backup' in url_lower or 'alt' in url_lower:
        score -= 5
    
    return score

def fetch_iptv_org_streams():
    """Fetch streams from iptv-org database"""
    print("Fetching fresh streams from iptv-org...")
    
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
    
    # Remove common suffixes for better matching
    channel_name_clean = channel_name_upper.replace('(TEMPORARY)', '').replace('GEO-BLOCKED', '').replace('(LATENCY)', '').strip()
    
    # Common channel name mappings
    channel_mappings = {
        'FOX NEWS': ['FOX NEWS', 'FOXNEWS', 'FOX', 'FNC'],
        'CBSN': ['CBS NEWS', 'CBSN', 'CBS'],
        'ABC NEWS': ['ABC NEWS', 'ABCNEWS', 'ABC'],
        'CNN': ['CNN'],
        'OANN': ['OAN', 'ONE AMERICA NEWS', 'OANN'],
        'NEWSMAX TV': ['NEWSMAX', 'NEWSMAX TV'],
        'MSNBC': ['MSNBC'],
        'BBC NEWS': ['BBC', 'BBC NEWS', 'BBC AMERICA', 'BBCAMERICA'],
        'TBN': ['TBN', 'TRINITY'],
        'TCM': ['TCM', 'TURNER CLASSIC MOVIES'],
        'AMC': ['AMC'],
        'TNT': ['TNT'],
        'TBS': ['TBS'],
        'TRUTV': ['TRUTV', 'TRU TV'],
        'HLN': ['HLN', 'HEADLINE NEWS'],
        'CARTOON NETWORK': ['CARTOON NETWORK', 'CN'],
        'NICKTOONS': ['NICKTOONS', 'NICKELODEON'],
        'DISNEY CHANNEL': ['DISNEY CHANNEL', 'DISNEY'],
        'ESPN': ['ESPN'],
        'ESPN2': ['ESPN2', 'ESPN 2'],
        'FS1': ['FOX SPORTS 1', 'FOX SPORTS1', 'FS1', 'FS 1'],
        'FOX SPORTS': ['FOX SPORTS'],
        'HBO': ['HBO'],
        'CINEMAX': ['CINEMAX'],
        'STADIUM': ['STADIUM'],
        'DISCOVERY': ['DISCOVERY', 'DISCOVERY CHANNEL'],
        'TLC': ['TLC'],
        'NATIONAL GEOGRAPHIC': ['NAT GEO', 'NATIONAL GEOGRAPHIC', 'NATGEO'],
        'MTV': ['MTV'],
        'CHARGE': ['CHARGE!', 'CHARGE'],
        'POP': ['POP', 'POP TV'],
        'BOOMERANG': ['BOOMERANG']
    }
    
    # Find matching channel names
    search_terms = []
    for key, values in channel_mappings.items():
        if any(term in channel_name_clean for term in values):
            search_terms.extend(values)
            break
    
    if not search_terms:
        search_terms = [channel_name_clean]
    
    print(f"  Searching for: {search_terms}")
    
    # Search through iptv-org streams with priority system
    exact_matches = []
    title_matches = []
    partial_matches = []
    
    for stream in iptv_streams:
        stream_name = stream.get('name', '').upper()
        stream_title = stream.get('title', '').upper()
        url = stream.get('url', '')
        
        if not url or '.m3u8' not in url.lower():
            continue
        
        candidate = {
            'name': stream.get('name') or stream.get('title', 'Unknown'),
            'url': url,
            'country': stream.get('country', ''),
            'title': stream.get('title', ''),
            'stream_name': stream_name,
            'stream_title': stream_title,
            'quality_score': get_stream_quality_score(url, stream, channel_name),
            'match_type': '',
            'mismatch_reason': stream.get('_mismatch_reason', None)
        }
        
        matched = False
        for term in search_terms:
            # Priority 1: Exact match in name field
            if stream_name and term == stream_name:
                candidate['match_type'] = 'EXACT_NAME'
                exact_matches.append(candidate)
                country_tag = f"[{stream.get('country', 'N/A')}]" if stream.get('country') else ""
                mismatch_tag = f" ⚠️{candidate['mismatch_reason']}" if candidate['mismatch_reason'] else ""
                print(f"    - EXACT match in name: {stream.get('name', 'Unknown')} {country_tag} [Q:{candidate['quality_score']}]{mismatch_tag} | {url[:45]}...")
                matched = True
                break
            
            # Priority 2: Exact match in title field
            elif stream_title and term == stream_title:
                candidate['match_type'] = 'EXACT_TITLE'
                title_matches.append(candidate)
                country_tag = f"[{stream.get('country', 'N/A')}]" if stream.get('country') else ""
                mismatch_tag = f" ⚠️{candidate['mismatch_reason']}" if candidate['mismatch_reason'] else ""
                print(f"    - Exact match in title: {stream.get('title', 'Unknown')} {country_tag} [Q:{candidate['quality_score']}]{mismatch_tag} | {url[:45]}...")
                matched = True
                break
        
        if not matched:
            for term in search_terms:
                if stream_name and term in stream_name:
                    candidate['match_type'] = 'PARTIAL_NAME'
                    partial_matches.append(candidate)
                    country_tag = f"[{stream.get('country', 'N/A')}]" if stream.get('country') else ""
                    mismatch_tag = f" ⚠️{candidate['mismatch_reason']}" if candidate['mismatch_reason'] else ""
                    print(f"    - Partial match in name: {stream.get('name', 'Unknown')} {country_tag} [Q:{candidate['quality_score']}]{mismatch_tag} | {url[:45]}...")
                    matched = True
                    break
        
        if not matched:
            for term in search_terms:
                if stream_title and term in stream_title:
                    candidate['match_type'] = 'PARTIAL_TITLE'
                    partial_matches.append(candidate)
                    country_tag = f"[{stream.get('country', 'N/A')}]" if stream.get('country') else ""
                    mismatch_tag = f" ⚠️{candidate['mismatch_reason']}" if candidate['mismatch_reason'] else ""
                    print(f"    - Partial match in title: {stream.get('title', 'Unknown')} {country_tag} [Q:{candidate['quality_score']}]{mismatch_tag} | {url[:45]}...")
                    break
    
    # Sort each category by quality score (highest first)
    exact_matches.sort(key=lambda x: x['quality_score'], reverse=True)
    title_matches.sort(key=lambda x: x['quality_score'], reverse=True)
    partial_matches.sort(key=lambda x: x['quality_score'], reverse=True)
    
    # Combine in priority order
    candidates = exact_matches + title_matches + partial_matches
    
    print(f"  Found {len(candidates)} potential replacements (Exact: {len(exact_matches)}, Title: {len(title_matches)}, Partial: {len(partial_matches)})")
    
    # Test each candidate until we find one that works
    for i, candidate in enumerate(candidates):
        display_name = candidate.get('title') or candidate.get('name', 'Unknown')
        quality = candidate['quality_score']
        match_type = candidate.get('match_type', 'UNKNOWN')
        
        print(f"  Testing candidate {i+1}/{len(candidates)}: {display_name} ({candidate['country']}) [Quality:{quality}] [{match_type}]")
        print(f"    URL: {candidate['url']}")
        
        if check_m3u8_link(candidate['url']):
            print(f"  ✓ Found working replacement!")
            return candidate['url']
        
        time.sleep(1)
    
    return None

def should_upgrade_stream(current_url, current_country, channel_title, iptv_streams):
    """Check if there's a better quality/country stream available than the current one"""
    print(f"  Checking for better alternatives to current stream...")
    
    current_score = get_stream_quality_score(current_url, {'country': current_country or ''}, channel_title)
    print(f"    Current stream score: {current_score} [Country: {current_country or 'Unknown'}]")
    
    channel_name_upper = channel_title.upper()
    channel_name_clean = channel_name_upper.replace('(TEMPORARY)', '').replace('GEO-BLOCKED', '').replace('(LATENCY)', '').strip()
    
    channel_mappings = {
        'FOX NEWS': ['FOX NEWS', 'FOXNEWS', 'FOX', 'FNC'],
        'CBSN': ['CBS NEWS', 'CBSN', 'CBS'],
        'ABC NEWS': ['ABC NEWS', 'ABCNEWS', 'ABC'],
        'CNN': ['CNN'],
        'OANN': ['OAN', 'ONE AMERICA NEWS', 'OANN'],
        'NEWSMAX TV': ['NEWSMAX', 'NEWSMAX TV'],
        'MSNBC': ['MSNBC'],
        'BBC NEWS': ['BBC', 'BBC NEWS', 'BBC AMERICA', 'BBCAMERICA'],
        'TBN': ['TBN', 'TRINITY'],
        'TCM': ['TCM', 'TURNER CLASSIC MOVIES'],
        'AMC': ['AMC'],
        'TNT': ['TNT'],
        'TBS': ['TBS'],
        'TRUTV': ['TRUTV', 'TRU TV'],
        'HLN': ['HLN', 'HEADLINE NEWS'],
        'CARTOON NETWORK': ['CARTOON NETWORK', 'CN'],
        'NICKTOONS': ['NICKTOONS', 'NICKELODEON'],
        'DISNEY CHANNEL': ['DISNEY CHANNEL', 'DISNEY'],
        'ESPN': ['ESPN'],
        'ESPN2': ['ESPN2', 'ESPN 2'],
        'FS1': ['FOX SPORTS 1', 'FOX SPORTS1', 'FS1', 'FS 1'],
        'FOX SPORTS': ['FOX SPORTS'],
        'HBO': ['HBO'],
        'CINEMAX': ['CINEMAX'],
        'STADIUM': ['STADIUM'],
        'DISCOVERY': ['DISCOVERY', 'DISCOVERY CHANNEL'],
        'TLC': ['TLC'],
        'NATIONAL GEOGRAPHIC': ['NAT GEO', 'NATIONAL GEOGRAPHIC', 'NATGEO'],
        'MTV': ['MTV'],
        'CHARGE': ['CHARGE!', 'CHARGE'],
        'POP': ['POP', 'POP TV'],
        'BOOMERANG': ['BOOMERANG']
    }
    
    search_terms = []
    for key, values in channel_mappings.items():
        if any(term in channel_name_clean for term in values):
            search_terms.extend(values)
            break
    
    if not search_terms:
        search_terms = [channel_name_clean]
    
    best_alternative = None
    best_score = current_score + 20  # Require at least 20 points improvement
    
    for stream in iptv_streams:
        stream_name = stream.get('name', '').upper()
        stream_title = stream.get('title', '').upper()
        search_text = f"{stream_name} {stream_title}"
        
        matched = False
        for term in search_terms:
            if term in search_text:
                matched = True
                break
        
        if not matched:
            continue
        
        url = stream.get('url', '')
        if not url or '.m3u8' not in url.lower():
            continue
        
        if url == current_url:
            continue
        
        alt_score = get_stream_quality_score(url, stream, channel_title)
        
        if alt_score > best_score:
            best_alternative = {
                'url': url,
                'score': alt_score,
                'name': stream.get('title') or stream.get('name', 'Unknown'),
                'country': stream.get('country', '')
            }
            best_score = alt_score
    
    if best_alternative:
        improvement = best_score - current_score
        reason = f"Found better stream: {best_alternative['name']} [{best_alternative['country']}] (Score: {best_score} vs {current_score}, +{improvement} improvement)"
        print(f"    ✓ {reason}")
        return (True, best_alternative['url'], reason)
    
    print(f"    No better alternatives found")
    return (False, None, None)

def update_advancefeed():
    """Main function to update dead links in advancefeed.json"""
    print("Starting IPTV Link Fixer...")
    print(f"Current time: {datetime.now()}")
    
    try:
        with open('advancefeed.json', 'r') as f:
            feed_data = json.load(f)
    except FileNotFoundError:
        print("Error: advancefeed.json not found!")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing advancefeed.json: {e}")
        return
    
    iptv_streams = fetch_iptv_org_streams()
    
    if not iptv_streams:
        print("No streams fetched from iptv-org. Exiting.")
        return
    
    updated_count = 0
    checked_count = 0
    failed_count = 0
    upgraded_count = 0
    
    if 'shortFormVideos' in feed_data:
        for video in feed_data['shortFormVideos']:
            checked_count += 1
            
            channel_title = video.get('title', 'Unknown')
            channel_id = video.get('id', 'Unknown')
            
            print(f"\n{'='*70}")
            print(f"[{checked_count}] Checking: {channel_title} ({channel_id})")
            print(f"{'='*70}")
            
            content = video.get('content', {})
            videos = content.get('videos', [])
            
            if not videos:
                print("  No video URLs found")
                continue
            
            video_obj = videos[0]
            current_url = video_obj.get('url', '')
            
            if not current_url:
                print("  No URL found")
                continue
            
            print(f"  Current URL: {current_url}")
            
            print(f"  Testing if stream actually works...")
            is_working = check_m3u8_link(current_url)
            
            if is_working:
                print("  ✓ Link is working and streaming")
                
                should_upgrade, new_url, reason = should_upgrade_stream(
                    current_url, 
                    video.get('country', ''),
                    channel_title, 
                    iptv_streams
                )
                
                if should_upgrade and new_url:
                    print(f"  → UPGRADE AVAILABLE: {reason}")
                    print(f"  Testing new stream before upgrading...")
                    
                    if check_m3u8_link(new_url):
                        video_obj['url'] = new_url
                        upgraded_count += 1
                        updated_count += 1
                        print(f"  ✓✓✓ UPGRADED to: {new_url}")
                    else:
                        print(f"  ✗ New stream doesn't work, keeping current")
                
                continue
            
            print("  ✗ Link is dead or not streaming, searching for replacement...")
            failed_count += 1
            
            new_url = find_replacement_stream(channel_title, iptv_streams)
            
            if new_url:
                video_obj['url'] = new_url
                updated_count += 1
                print(f"  ✓✓✓ UPDATED to: {new_url}")
            else:
                print(f"  ✗✗✗ No working replacement found")
            
            time.sleep(1)
    
    if updated_count > 0:
        feed_data['lastUpdated'] = datetime.now().isoformat()
        
        with open('advancefeed.json', 'w') as f:
            json.dump(feed_data, f, indent=2)
        
        print(f"\n{'='*70}")
        print(f"✓ Update complete!")
        print(f"  Channels checked: {checked_count}")
        print(f"  Dead channels found: {failed_count}")
        print(f"  Channels fixed (dead → working): {updated_count - upgraded_count}")
        print(f"  Channels upgraded (working → better): {upgraded_count}")
        print(f"  Total channels updated: {updated_count}")
        print(f"  Still broken: {failed_count - (updated_count - upgraded_count)}")
        print(f"  Last updated: {feed_data['lastUpdated']}")
        print(f"{'='*70}")
    else:
        print(f"\n{'='*70}")
        if failed_count > 0:
            print(f"Found {failed_count} dead channels but no working replacements available.")
        elif upgraded_count > 0:
            print(f"Upgraded {upgraded_count} channels to better streams!")
        else:
            print(f"No updates needed. All {checked_count} channels are working optimally.")
        print(f"{'='*70}")

if __name__ == "__main__":
    update_advancefeed()