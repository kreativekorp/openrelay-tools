#!/usr/bin/env python

from __future__ import print_function
import struct
import sys


OS_2 = 0x4F532F32
HEAD = 0x68656164
HHEA = 0x68686561
CHKSUM = 0xB1B0AFBA
UINT_MAX = 0xFFFFFFFF
NULLS = '\x00\x00\x00\x00'.encode('utf8')
SPACES = '\x20\x20\x20\x20'.encode('utf8')

byteStruct = struct.Struct('>B')
shortStruct = struct.Struct('>H')
intStruct = struct.Struct('>I')
ttfHeaderStruct = struct.Struct('>IHHHH')
ttfTableStruct = struct.Struct('>IIII')

def chksum(data):
	cs = 0
	nl = len(data) ^ (len(data) & 3)
	for i in range(0, nl, 4):
		cs += intStruct.unpack(data[i:(i+4)])[0]
		cs &= UINT_MAX
	for i in range(nl, len(data)):
		cs += byteStruct.unpack(data[i:(i+1)])[0] << (((i & 3) ^ 3) << 3)
		cs &= UINT_MAX
	return cs

class TtfTable:
	def __init__(self, tag, checksum, offset, length):
		self.tag = tag
		self.checksum = checksum
		self.offset = offset
		self.length = length
		self.data = None

class TtfFile:
	def __init__(self, path):
		fp = open(path, 'rb')
		self.scaler, self.numTables, self.searchRange, self.entrySelector, self.rangeShift = ttfHeaderStruct.unpack(fp.read(12))
		self.tables = [TtfTable(*ttfTableStruct.unpack(fp.read(16))) for i in range(0, self.numTables)]
		for table in self.tables:
			fp.seek(table.offset)
			table.data = fp.read(table.length)
		fp.close()

	def getTable(self, tag):
		for table in self.tables:
			if table.tag == tag:
				return table
		return None

	def getData(self, tag, offset=None, length=None, decode=None):
		for table in self.tables:
			if table.tag == tag:
				data = table.data
				if offset is not None:
					data = data[offset:]
				if length is not None:
					data = data[:length]
				if decode is not None:
					data = decode(data)
				return data
		return None

	def setData(self, tag, data, offset=None, length=None, encode=None):
		for table in self.tables:
			if table.tag == tag:
				if encode is not None:
					data = encode(data)
				if offset is None and length is None:
					table.data = data
				if offset is None and length is not None:
					table.data = data + table.data[length:]
				if offset is not None and length is None:
					table.data = table.data[:offset] + data
				if offset is not None and length is not None:
					table.data = table.data[:offset] + data + table.data[offset+length:]
				return True
		return False

	def write(self, path):
		# Calculate header values.
		self.numTables = len(self.tables)
		self.searchRange = 1 << 30
		self.entrySelector = 30
		while self.searchRange > self.numTables:
			self.searchRange >>= 1
			self.entrySelector -= 1
		self.searchRange <<= 4
		self.rangeShift = (self.numTables << 4) - self.searchRange

		# Calculate offsets.
		checksumLoc = 0
		currentLoc = 12 + (self.numTables << 4)
		self.tables.sort(key=lambda table: table.offset)
		for table in self.tables:
			if table.tag == HEAD:
				# Clear the whole-file checksum in the 'head' table.
				table.data = table.data[0:8] + NULLS[0:4] + table.data[12:]
				# Note where the whole-file checksum ends up.
				checksumLoc = currentLoc + 8
			table.checksum = chksum(table.data)
			table.offset = currentLoc
			table.length = len(table.data)
			currentLoc += table.length
			while currentLoc & 3:
				currentLoc += 1

		# Compile.
		ttf = [ttfHeaderStruct.pack(self.scaler, self.numTables, self.searchRange, self.entrySelector, self.rangeShift)]
		self.tables.sort(key=lambda table: table.tag)
		for table in self.tables:
			ttf.append(ttfTableStruct.pack(table.tag, table.checksum, table.offset, table.length))
		self.tables.sort(key=lambda table: table.offset)
		for table in self.tables:
			ttf.append(table.data)
			if table.length & 3:
				ttf.append(NULLS[(table.length & 3) : 4])
		data = ''.encode('utf8').join(ttf)
		if checksumLoc:
			# Update the whole-file checksum in the 'head' table.
			checksum = intStruct.pack((CHKSUM - chksum(data)) & UINT_MAX)
			data = data[0:checksumLoc] + checksum + data[(checksumLoc+4):]

		fp = open(path, 'wb')
		fp.write(data)
		fp.close()


def signedToUnsigned16(v):
	if 0 <= v < 0x8000:
		return v
	if -0x8000 <= v < 0:
		return v + 0x10000
	raise OverflowError(v)

def unsignedToSigned16(v):
	if 0 <= v < 0x8000:
		return v
	if 0x8000 <= v < 0x10000:
		return v - 0x10000
	raise OverflowError(v)

decodeFCC = lambda d: d.decode('us-ascii')
decodeUShort = lambda d: shortStruct.unpack(d)[0]
decodeShort = lambda d: unsignedToSigned16(shortStruct.unpack(d)[0])

encodeFCC = lambda d: (d.encode('us-ascii') + SPACES)[0:4]
encodeUShort = lambda d: shortStruct.pack(int(d))
encodeShort = lambda d: shortStruct.pack(signedToUnsigned16(int(d)))

getters = {
	'vendorId': lambda ttf: ttf.getData(OS_2, 0x3A, 4, decodeFCC),
	'typoAscent': lambda ttf: ttf.getData(OS_2, 0x44, 2, decodeShort),
	'typoDescent': lambda ttf: ttf.getData(OS_2, 0x46, 2, decodeShort),
	'typoLineGap': lambda ttf: ttf.getData(OS_2, 0x48, 2, decodeShort),
	'winAscent': lambda ttf: ttf.getData(OS_2, 0x4A, 2, decodeUShort),
	'winDescent': lambda ttf: ttf.getData(OS_2, 0x4C, 2, decodeUShort),
	'xHeight': lambda ttf: ttf.getData(OS_2, 0x56, 2, decodeShort),
	'capHeight': lambda ttf: ttf.getData(OS_2, 0x58, 2, decodeShort),
	'unitsPerEm': lambda ttf: ttf.getData(HEAD, 0x12, 2, decodeUShort),
	'xMin': lambda ttf: ttf.getData(HEAD, 0x24, 2, decodeShort),
	'yMin': lambda ttf: ttf.getData(HEAD, 0x26, 2, decodeShort),
	'xMax': lambda ttf: ttf.getData(HEAD, 0x28, 2, decodeShort),
	'yMax': lambda ttf: ttf.getData(HEAD, 0x2A, 2, decodeShort),
	'hheaAscent': lambda ttf: ttf.getData(HHEA, 0x04, 2, decodeShort),
	'hheaDescent': lambda ttf: ttf.getData(HHEA, 0x06, 2, decodeShort),
	'hheaLineGap': lambda ttf: ttf.getData(HHEA, 0x08, 2, decodeShort),
}

setters = {
	'vendorId': lambda ttf, d: ttf.setData(OS_2, d, 0x3A, 4, encodeFCC),
	'typoAscent': lambda ttf, d: ttf.setData(OS_2, d, 0x44, 2, encodeShort),
	'typoDescent': lambda ttf, d: ttf.setData(OS_2, d, 0x46, 2, encodeShort),
	'typoLineGap': lambda ttf, d: ttf.setData(OS_2, d, 0x48, 2, encodeShort),
	'winAscent': lambda ttf, d: ttf.setData(OS_2, d, 0x4A, 2, encodeUShort),
	'winDescent': lambda ttf, d: ttf.setData(OS_2, d, 0x4C, 2, encodeUShort),
	'xHeight': lambda ttf, d: ttf.setData(OS_2, d, 0x56, 2, encodeShort),
	'capHeight': lambda ttf, d: ttf.setData(OS_2, d, 0x58, 2, encodeShort),
	'unitsPerEm': lambda ttf, d: ttf.setData(HEAD, d, 0x12, 2, encodeUShort),
	'xMin': lambda ttf, d: ttf.setData(HEAD, d, 0x24, 2, encodeShort),
	'yMin': lambda ttf, d: ttf.setData(HEAD, d, 0x26, 2, encodeShort),
	'xMax': lambda ttf, d: ttf.setData(HEAD, d, 0x28, 2, encodeShort),
	'yMax': lambda ttf, d: ttf.setData(HEAD, d, 0x2A, 2, encodeShort),
	'hheaAscent': lambda ttf, d: ttf.setData(HHEA, d, 0x04, 2, encodeShort),
	'hheaDescent': lambda ttf, d: ttf.setData(HHEA, d, 0x06, 2, encodeShort),
	'hheaLineGap': lambda ttf, d: ttf.setData(HHEA, d, 0x08, 2, encodeShort),
}


def printHelp():
	print()
	print('ttfhack - Inspect or modify certain values in TrueType files.')
	print()
	print('  sf=<path>             Read arguments from text file.')
	print('  if=<path>             Read tables from TrueType file.')
	print('  of=<path>             Write tables to TrueType file.')
	print('  vendorId[=<str>]      Inspect or modify OS/2 vendor ID.')
	print('  typoAscent[=<int>]    Inspect or modify OS/2 typo ascent.')
	print('  typoDescent[=<int>]   Inspect or modify OS/2 typo descent.')
	print('  typoLineGap[=<int>]   Inspect or modify OS/2 typo line gap.')
	print('  winAscent[=<int>]     Inspect or modify OS/2 winAscent.')
	print('  winDescent[=<int>]    Inspect or modify OS/2 winDescent.')
	print('  xHeight[=<int>]       Inspect or modify OS/2 x height.')
	print('  capHeight[=<int>]     Inspect or modify OS/2 cap height.')
	print('  unitsPerEm[=<int>]    Inspect or modify units per em.')
	print('  xMin[=<int>]          Inspect or modify bounding box xMin.')
	print('  yMin[=<int>]          Inspect or modify bounding box yMin.')
	print('  xMax[=<int>]          Inspect or modify bounding box xMax.')
	print('  yMax[=<int>]          Inspect or modify bounding box yMax.')
	print('  hheaAscent[=<int>]    Inspect or modify hhea ascent.')
	print('  hheaDescent[=<int>]   Inspect or modify hhea descent.')
	print('  hheaLineGap[=<int>]   Inspect or modify hhea line gap.')
	print()

class CommandProcessor:
	def __init__(self):
		self.ttf = None
		self.changed = False
		self.error = None

	def processArgs(self, args):
		for arg in args:
			self.processArg(arg)

	def processArg(self, arg):
		if self.error is not None:
			return
		elif '=' in arg:
			self.processSet(*arg.split('=', 1))
		else:
			self.processGet(arg)

	def processGet(self, getter):
		if getter == 'help':
			printHelp()
			self.error = False
		elif getter not in getters:
			self.error = 'Unknown command: %s' % getter
		elif self.ttf is None:
			self.error = 'No input file specified for %s' % getter
		else:
			print(getters[getter](self.ttf))

	def processSet(self, setter, data):
		if setter == 'sf':
			with open(data, 'r') as args:
				self.processArgs(args)
		elif setter == 'if':
			if self.changed:
				self.error = 'No output file specified before %s=%s' % (setter, data)
				return
			self.ttf = TtfFile(data)
			self.changed = False
		elif self.ttf is None:
			self.error = 'No input file specified for %s=%s' % (setter, data)
		elif setter == 'of':
			self.ttf.write(data)
			self.changed = False
		elif setter not in setters:
			self.error = 'Unknown command: %s=%s' % (setter, data)
		elif setters[setter](self.ttf, data):
			self.changed = True
		else:
			self.error = 'Could not find table for %s=%s' % (setter, data)

	def close(self):
		if self.error is not None:
			return
		elif self.changed:
			self.error = 'No output file specified'
		elif self.ttf is None:
			self.error = 'No input file specified'

def main():
	args = sys.argv[1:]
	if not args:
		printHelp()
		return
	cmd = CommandProcessor()
	cmd.processArgs(args)
	cmd.close()
	if cmd.error:
		print(cmd.error)

if __name__ == '__main__':
	main()
