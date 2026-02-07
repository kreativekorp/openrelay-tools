#!/usr/bin/env python

from __future__ import print_function
import urllib.request
import json

words_url = 'https://api.linku.la/v1/words'
sandbox_url = 'https://api.linku.la/v1/sandbox'
request_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

words = None
sandbox = None

def getWords():
	global words
	if words is None:
		try:
			req = urllib.request.Request(words_url, headers=request_headers)
			with urllib.request.urlopen(req) as response:
				source = response.read().decode('utf-8')
				words = json.loads(source)
				try:
					with open('linku_words.json', 'w') as f:
						f.write(source)
				except:
					pass
		except:
			with open('linku_words.json', 'r') as f:
				words = json.load(f)
	return words

def getSandbox():
	global sandbox
	if sandbox is None:
		try:
			req = urllib.request.Request(sandbox_url, headers=request_headers)
			with urllib.request.urlopen(req) as response:
				source = response.read().decode('utf-8')
				sandbox = json.loads(source)
				try:
					with open('linku_sandbox.json', 'w') as f:
						f.write(source)
				except:
					pass
		except:
			with open('linku_sandbox.json', 'r') as f:
				sandbox = json.load(f)
	return sandbox

if __name__ == '__main__':
	for word in getWords().keys():
		print('%s\t%s' % (word, getWords()[word]['usage_category']))
	for word in getSandbox().keys():
		print('%s\t%s' % (word, getSandbox()[word]['usage_category']))
