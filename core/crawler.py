import os
import re
import requests
import codecs
import sys
import threading
import subprocess
import time
import random
from queue import Queue
from bs4 import BeautifulSoup

user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36'

default_tread_count = 10
q = Queue()
workers = []
merge_cmd = ''
fail_count = 0
video_title = 'video'
descriptor_content = {}
file_parts = {}

class DlWorker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        print('Start ', self.getName())

    def run(self):
        global fail_count
        # To avoid request storm, wait an random short time per thread
        a_short_while = random.randint(1,5)
        time.sleep(a_short_while)
        while not q.empty():
            part_source, part = q.get()
            
            # May already be there in previous incomplete download
            filename = '../Videos/{}/{}'.format(video_title, part)
            if os.path.exists(filename):
                file_parts[part]['dl'] = True
                print('file part - %-16s already exists' % part)
                continue

            return_code = 1
            while return_code != 0:
                return_code = self.wget(source=part_source, name=part, method='built-in')
                if return_code != 0:
                    fail_count += 1

                succeed = 'OK' if return_code == 0 else 'Fail'
                print('Thread - %-9s, file part - %-16s, %s' % (self.getName(), part, succeed))

                max_delay_time = 10 if fail_count < 10 else 20
                another_short_while = random.randint(1, max_delay_time)
                time.sleep(another_short_while)

    def wget(self, source='', name='', cmd='', method='built-in'):
        if method == 'third-party':
            process = subprocess.Popen(['/bin/bash', '-c', cmd], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, universal_newlines=True)
            return_code = process.wait()
            return return_code
        elif method == 'built-in':
            s = requests.Session()
            s.headers['User-Agent'] = user_agent
            r = s.get(source, timeout=90)
            if r.status_code != 200:
                s.close()
                return -1*r.status_code

            folder_name = '../Videos/{}'.format(video_title)
            if (not os.path.exists(folder_name)):
                os.mkdir(folder_name)

            with open(folder_name + "/" + name, 'wb') as fd:
                for chunk in r.iter_content(chunk_size=128):
                    fd.write(chunk)
            file_parts[name]['dl'] = True

            s.close()
            return 0

def dl_start(worker_count=default_tread_count):
    global workers
    for i in range(worker_count):
        worker = DlWorker()
        workers.append(worker)
        worker.start()

# For website - https://cableav.tv
def extract_descripter_source(url, ua = user_agent):
    global video_title
    s = requests.Session()
    s.headers['User-Agent'] = ua
    response = s.get(url)

    # parse video title
    soup = BeautifulSoup(response.text, 'html.parser')
    for h in soup.find_all('h1'):
        if str(['entry-title', 'extra-bold', 'h-font-size-30', 'h1-tablet']) == str(h['class']):
            video_title = h.string
            break

    # parse video source
    p = re.compile(r'"source_file":"https:.*?"')
    contents = p.findall(response.text)
    urls = []
    prefix = []
    if len(contents) > 0:
        for c in contents:
            url = c[c.index(":")+1:].strip('"').replace('\\', '')
            urls.append(url)
            prefix.append(url[:url.find("index.m3u8")])

        i = 0
        for url in urls:
            response = s.get(url)            
            descriptor_content[i] = list(response.text.split('\n'))
            i += 1    
    
    s.close()
    return prefix[0]

def parse_file_parts(prefix, ua = user_agent, resolution = 0):
    if resolution > (len(descriptor_content) - 1):
        print('Invalid resolution, should from {} to {}'.format(0, len(descriptor_content) - 1))
        return

    p = re.compile('^CLS')
    contents_by_line = []
    for l in descriptor_content[resolution]:
        if p.match(l):
            contents_by_line.append(l)

    for l in contents_by_line:
        part_name = l[0:l.index('?')]
        part_source = prefix + l
        q.put((part_source, part_name))
        file_parts[part_name] = {'src': part_source, 'dl': False}

def merge_file_parts():
    video_folder = '../Videos/'+video_title+'/'
    with open(video_folder + video_title+'.ts', 'wb') as outfile:
        for k, v in file_parts.items():
            if v['dl']:
                # print('Merging {}'.format(k))
                with open(video_folder + k, 'rb') as infile:
                    outfile.write(infile.read())
            else:
                print('skip file part - {}'.format(k))
    
def crawler_proceed():
    url = sys.argv[1]
    prefix = extract_descripter_source(url)

    if len(prefix) > 0:
        parse_file_parts(prefix)

    dl_start()

    for w in workers:
        w.join()

    merge_file_parts()

if __name__ == '__main__':
    crawler_proceed()    
