import requests
import re
import os
import sys
import time
import threading
import random
import subprocess
from Crypto.Cipher import AES
from binascii import hexlify, unhexlify
from queue import Queue

'''
    sample video descriptor url:
    https://kingdom-b.alonestreaming.com/hls/Wxjts3E6TSYZt8iSzcLx3Q/1627112054/16000/16180/16180.m3u8

    sample video part url:
    https://kingdom-b.alonestreaming.com/hls/Wxjts3E6TSYZt8iSzcLx3Q/1627112054/16000/16180/161801.ts
'''

fail_count = 0
descriptor_name_without_suffix = ''
descriptor_contents = []
# url = "https://jable.tv/videos/mide-932/"
user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36'
file_parts = {}
folder_name = ''
q = Queue()
video_title = 'video'
workers = []
default_tread_count = 10
key_file_name = ''
iv = ''
key = ''

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

            # folder_name = '../Videos/{}'.format(video_title)
            # if (not os.path.exists(folder_name)):
            #     os.mkdir(folder_name)

            with open(folder_name + "/" + name, 'wb') as fd:
                for chunk in r.iter_content(chunk_size=128):
                    fd.write(chunk)
            file_parts[name]['dl'] = True

            s.close()
            return 0


# For website - https://jable.tv/
def extract_descripter_source(url, ua = user_agent):
    global video_title
    global descriptor_contents
    global descriptor_name_without_suffix
    global key_file_name
    global iv

    s = requests.Session()
    s.headers['User-Agent'] = user_agent
    response = s.get(url)    

    regexp = re.compile(r'<meta\sproperty="og:title"\scontent=.+\s\/>')
    matches = regexp.findall(response.text)
    if len(matches) > 0:
        meta = matches[0]
        content_tag_start = meta.index("content=") + len("content=\"")
        content_tag_end = meta.rfind("\"")
        video_title = meta[content_tag_start:content_tag_end]

        regexp = re.compile(r'var hlsUrl =.*;')
        contents = regexp.findall(response.text)
        if len(contents) > 0:
            parts = contents[0].split()
            descriptor_url = parts[3][0:len(parts[3])-1].strip("\'")
            descriptor_name_without_suffix = descriptor_url[descriptor_url.rfind("/")+1:len(descriptor_url)-len(".m3u8")]
            response = s.get(descriptor_url)        
            regexp = re.compile(descriptor_name_without_suffix+r'[0-9]+\.ts')
            descriptor_contents = regexp.findall(response.text)
            
            # parse key file
            regexp = re.compile(r'URI="[0-9a-zA-Z]+\.ts"')
            matches = regexp.findall(response.text)
            if len(matches) == 0:
                print('key file not found!')
                return None
            
            _, _, key_file_name = matches[0].partition('=')
            key_file_name = key_file_name.strip("\"")
            # print(key_file_name)

            # parse iv value
            regexp = re.compile(r'IV=0x[0-9a-zA-Z]+')
            matches = regexp.findall(response.text)
            if len(matches) == 0:
                print('iv not found!')
                return None

            _, _, iv = matches[0].partition('=')
            # print(iv)
            
            s.close()
            return descriptor_url

    s.close()
    return None

def parse_file_parts(url_prefix):    
    for part_name in descriptor_contents:
        part_source = url_prefix + part_name
        q.put((part_source, part_name))
        file_parts[part_name] = {'src': part_source, 'dl': False}
    # print(file_parts)

def retrive_key(key_file_url):
    s = requests.Session()
    s.headers['User-Agent'] = user_agent
    response = s.get(key_file_url)    
    # print(response.content)
    content = response.content
    s.close()
    return content

def decrypt(file_part, key, iv):
    ct_bytes = b''

    with open(file_part, mode='rb') as file:
        ct_bytes = file.read()
    
    decipher = AES.new(key, AES.MODE_CBC, iv)
    pt = decipher.decrypt(ct_bytes)
    
    with open(file_part, mode='w+b') as file:
        file.write(pt)

def dl_start(worker_count=default_tread_count):
    global workers
    for i in range(worker_count):
        worker = DlWorker()
        workers.append(worker)
        worker.start()

if __name__ == '__main__':
    url = sys.argv[1]
    descriptor_url = extract_descripter_source(url)
    url_prefix = descriptor_url[0:descriptor_url.rfind("/")+1]
    key = retrive_key(url_prefix+"/"+key_file_name)
    iv = hexlify(iv)
    
    parse_file_parts(url_prefix)

    # prepare tmp folder to store video parts
    workding_dir = os.getcwd()
    folder_name = os.path.join(workding_dir, "../Videos", descriptor_name_without_suffix)
    if not os.path.exists(folder_name):
        os.mkdir(folder_name, mode=0o755)

    dl_start()

    for w in workers:
        w.join()