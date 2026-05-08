import urllib.request
import re
url = 'http://127.0.0.1:8000/services/'
req = urllib.request.Request(url)
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    matches = re.findall(r'src="([^"]+)"[^>]*alt="([^"]+)"', html)
    with open('test_out.txt', 'w', encoding='utf-8') as f:
        for src, alt in matches:
            f.write(f'Alt: {alt}, Src: {src}\n')
except Exception as e:
    print('Error:', e)
