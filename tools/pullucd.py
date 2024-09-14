#!/usr/bin/env python

from __future__ import print_function
import os
import re
import subprocess
import sys
import zipfile

def download(url, path):
	args = ['curl', '-L', '-s', url, '-o', path]
	subprocess.check_call(args)

def read_index(url):
	args = ['curl', '-L', '-s', url]
	proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	(out, err) = proc.communicate()
	return re.findall(r'<a href="([^"]+)">\1</a>', out.decode('utf-8'))

def read_index_recursive(url):
	for name in read_index(url):
		yield name
		if name.endswith('/'):
			for child in read_index_recursive(url + name):
				yield name + child

def read_versions():
	url = 'https://www.unicode.org/Public/'
	for v in read_index(url):
		if re.match(r'^[0-9]+([.][0-9]+)+/$', v):
			yield v[0:-1]

def latest_version():
	return '.'.join(str(p) for p in max(tuple(int(p) for p in v.split('.')) for v in read_versions()))

def read_ucd_index(v):
	url = 'https://www.unicode.org/Public/%s/ucd/' % v
	for name in read_index_recursive(url):
		if name.endswith('.txt'):
			yield name

def download_ucd(v, path):
	url = 'https://www.unicode.org/Public/%s/ucd/' % v
	for name in read_index_recursive(url):
		if name == 'Unihan.zip' or name.endswith('.txt'):
			basename = name.split('/')[-1]
			if basename != 'ReadMe.txt':
				dest = os.path.join(path, basename)
				if not os.path.exists(dest):
					print('Downloading version %s of %s...' % (v, basename))
					download(url + name, dest)
	unihan = os.path.join(path, 'Unihan.zip')
	if os.path.exists(unihan):
		with zipfile.ZipFile(unihan) as zip:
			for info in zip.infolist():
				if info.filename.endswith('.txt'):
					dest = os.path.join(path, info.filename)
					if not os.path.exists(dest):
						print('Extracting version %s of %s...' % (v, info.filename))
						zip.extract(info, path)

def download_ucd_all(path):
	for v in read_versions():
		dest = os.path.join(path, v)
		if not os.path.exists(dest):
			os.mkdir(dest)
		download_ucd(v, dest)


def main(args):
	def printHelp():
		print()
		print('pullucd - Download UCD data files from unicode.org.')
		print()
		print('  -d <path>             Specify destination directory.')
		print('  -v <maj>.<min>.<pt>   Download version by number.')
		print('  --latest              Download latest version.')
		print('  --all                 Download all versions.')
		print('  --version             Print latest version number.')
		print('  --versions            Print all version numbers.')
		print()
	if not args:
		printHelp()
		return
	parsingOptions = True
	multiple = False
	versions = []
	path = 'ucd'
	argi = 0
	while argi < len(args):
		arg = args[argi]
		argi += 1
		if parsingOptions and arg.startswith('-'):
			if arg == '--':
				parsingOptions = False
			elif arg == '-d' and argi < len(args):
				path = args[argi]
				argi += 1
			elif arg == '-v' and argi < len(args):
				if versions:
					multiple = True
				if args[argi] not in versions:
					versions.append(args[argi])
				argi += 1
			elif arg == '--latest':
				if versions:
					multiple = True
				v = latest_version()
				if v not in versions:
					versions.append(v)
			elif arg == '--all':
				multiple = True
				for v in read_versions():
					if v not in versions:
						versions.append(v)
			elif arg == '--multiple':
				multiple = True
			elif arg == '--version':
				print(latest_version())
				return
			elif arg == '--versions':
				for v in read_versions():
					print(v)
				return
			elif arg == '--help':
				printHelp()
				return
			else:
				print('Unknown option: %s' % arg)
				return
		elif re.match(r'^[0-9]+([.][0-9]+)+$', arg):
			if versions:
				multiple = True
			if arg not in versions:
				versions.append(arg)
		else:
			path = arg
	if not os.path.exists(path):
		os.mkdir(path)
	if len(versions) == 0:
		versions.append(latest_version())
	for v in versions:
		if multiple:
			dest = os.path.join(path, v)
			if not os.path.exists(dest):
				os.mkdir(dest)
			download_ucd(v, dest)
		else:
			download_ucd(v, path)


if __name__ == '__main__':
	main(sys.argv[1:])
