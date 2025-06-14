#!/usr/bin/env python3
# vim: set fileencoding=utf-8 :

__version__ = "1.0.6"

import sys
#from threading import Thread, Event
if sys.version_info.major >= 3:
#	from queue import Queue
	from io import StringIO
	StringTypes = [str]
else:
#	from Queue import Queue
	from StringIO import StringIO
	from types import StringTypes
from time import sleep
import signal
import termios, os, fcntl, atexit, select, locale

class NoKeyPressed(Exception):
	pass

# Hook for capturing "Window change" signals.
# Install this by calling:
# signal.signal(signal.SIGWINCH, sigwinchHook)
def sigwinchHook(signum, frame):
	try:
		Term.getSize()
		DotPrinterSlots.lock()
		DotPrinterSlots.refresh()
		DotPrinterSlots.release()
	except:
		pass

def textwidth(text):
	"""
	Returns the number of columns a given amount of text will take up,
	taking ANSI color escape sequences and dual-width characters
	into account.
	"""
	# Note: module "colors" is provided by the "ansicolors" package in pip.
	import colors, wcwidth
	return wcwidth.wcswidth(colors.strip_color(text))

def center(text, width, fillchar=' '):# {{{
	twidth = textwidth(text)
	if twidth >= width:
		return text
	lhs_pad = round((width - twidth) / 2)
	rhs_pad = width - (lhs_pad + twidth)
	return (fillchar * lhs_pad) + text + (fillchar * rhs_pad)
# }}}
def ljust(text, width, fillchar=' '):# {{{
	twidth = textwidth(text)
	if twidth >= width:
		return text
	pad = width - twidth
	return text + (fillchar * pad)
# }}}
def rjust(text, width, fillchar=' '):# {{{
	twidth = textwidth(text)
	if twidth >= width:
		return text
	pad = width - twidth
	return (fillchar * pad) + text
# }}}


class Term:# {{{
	"""	Static class representing the terminal.
		Doesn't do much yet, currently tracks window dimension changes,
		as well as providing a 'getkey' function.
	"""
	# Remember, these go COLS then ROWS
	size = (0, 0)
	_sizeChanged = False
	fd = None
	origattrs = None
	cursor_enabled = True
	advanced_pos = None
	advanced_lut = None
	fl = None
	initialized = False
	# Initialization function.  For best results, call this
	# before any other classmethods.
	@classmethod
	def init(cls):
		if cls.fd is None:
			signal.signal(signal.SIGWINCH, sigwinchHook)
			cls.getSize()
			cls.fd = sys.stdin.fileno()
			atexit.register(Term.cleanup)
		if cls.origattrs is None:
			try:
				cls.origattrs = termios.tcgetattr(cls.fd)
			except:
				pass
			# Vestigal, delete sometime next year...
			#new = termios.tcgetattr(cls.fd)
			#new[3] = new[3] & ~termios.ICANON & ~termios.ECHO & ~termios.ISIG
			#new[6][termios.VMIN] = 1
			#new[6][termios.VTIME] = 0
			#termios.tcsetattr(cls.fd, termios.TCSANOW, new)
		if cls.fl is None:
			cls.fl = fcntl.fcntl(cls.fd, fcntl.F_GETFL)
		cls.initialized = True
	# Puts terminal in 'raw' mode.
	@classmethod
	def raw(cls):
		new = termios.tcgetattr(cls.fd)
		new[3] = new[3] & ~termios.ICANON & ~termios.ECHO & ~termios.ISIG
		new[6][termios.VMIN] = 1
		new[6][termios.VTIME] = 0
		termios.tcsetattr(cls.fd, termios.TCSANOW, new)
	# Reverts any changes made to the terminal.
	@classmethod
	def revert(cls):
		termios.tcsetattr(cls.fd, termios.TCSANOW, cls.origattrs)
	# Enables 'canonical' mode.
	@classmethod
	def enableCanon(cls):
		new = termios.tcgetattr(cls.fd)
		new[3] = new[3] | termios.ICANON
		new[6][termios.VMIN] = cls.origattrs[6][termios.VMIN]
		new[6][termios.VTIME] = cls.origattrs[6][termios.VTIME]
		termios.tcsetattr(cls.fd, termios.TCSANOW, new)
	# Disables 'canonical' mode.
	@classmethod
	def disableCanon(cls, vmin=1, vtime=0):
		new = termios.tcgetattr(cls.fd)
		new[3] = new[3] & ~termios.ICANON
		new[6][termios.VMIN] = vmin
		new[6][termios.VTIME] = vtime
		termios.tcsetattr(cls.fd, termios.TCSANOW, new)
	# Enables local echo.
	@classmethod
	def enableEcho(cls):
		new = termios.tcgetattr(cls.fd)
		new[3] = new[3] | termios.ECHO
		termios.tcsetattr(cls.fd, termios.TCSANOW, new)
	# Disables local echo.
	@classmethod
	def disableEcho(cls):
		new = termios.tcgetattr(cls.fd)
		new[3] = new[3] & ~termios.ECHO
		termios.tcsetattr(cls.fd, termios.TCSANOW, new)
	# Allows the terminal to interpret incoming signals (like ^C)
	@classmethod
	def enableSig(cls):
		new = termios.tcgetattr(cls.fd)
		new[3] = new[3] | termios.ISIG
		termios.tcsetattr(cls.fd, termios.TCSANOW, new)
	# Disables signal interpretation.
	@classmethod
	def disableSig(cls):
		new = termios.tcgetattr(cls.fd)
		new[3] = new[3] & ~termios.ISIG
		termios.tcsetattr(cls.fd, termios.TCSANOW, new)
	# Turns off the cursor.
	@classmethod
	def disableCursor(cls):
		sys.stderr.buffer.write(b"\x1b[?25l")
		sys.stderr.buffer.flush()
		cls.cursor_enabled = False
	# Turns on the cursor.
	@classmethod
	def enableCursor(cls):
		sys.stderr.buffer.write(b"\x1b[?25h")
		sys.stderr.buffer.flush()
		cls.cursor_enabled = True
	# Reverts any changes made to the terminal.
	# Automatically called at script termination (provided you called init())
	@classmethod
	def cleanup(cls):
		if cls.origattrs is not None:
			termios.tcsetattr(cls.fd, termios.TCSAFLUSH, cls.origattrs)
		cls.enableCursor()
	@classmethod
	def getCursor(cls):
		import jlib
		if not cls.initialized:
			cls.init()
		blocking = cls.getblocking()
		if not blocking:
			cls.setblocking(True)
		sys.stderr.buffer.write(jlib.encapsulate_ansi('status').encode())
		sys.stderr.buffer.flush()
		retbuf = b''
		while True:
			char = cls.getkey()
			retbuf += char
			if char == b'R':
				break
		if not blocking:
			cls.setblocking(False)
		if retbuf.startswith(b"\x1b[") and retbuf.endswith(b'R'):
			retbuf = retbuf[2:-1]
		row, col = [ int(x) for x in retbuf.decode().split(';') ]
		return col, row
	@classmethod
	def setCursor(cls, col, row, flush=True):
		import jlib
		sys.stderr.write(jlib.encapsulate_ansi('cursor_position', [ "{}".format(x) for x in [row, col] ]))

		if flush:
			sys.stderr.flush()
	# Get one character from stdin.
	# Set interruptable=false if you don't want ^C to work.
	# By default, calling this blocks until a key is pressed. This behavior
	# can be changed by calling Term.setblocking(False). In this case, the
	# next available character in the input buffer is returned... if the input
	# buffer is empty, the NoKeyPressed exception is raised instead.
	@classmethod
	def getkey(cls, interruptable=True):
		if not cls.initialized:
			cls.init()
		try:
			orig = termios.tcgetattr(cls.fd)
		except termios.error:
			pass
		cls.disableCanon()
		cls.disableEcho()
		cls.disableSig()
		try:
			c = os.read(cls.fd, 1)
		except OSError:
			raise NoKeyPressed
		try:
			termios.tcsetattr(cls.fd, termios.TCSANOW, orig)
		except termios.error:
			pass
		if interruptable and c == b'\x03':
			raise KeyboardInterrupt
		return c
	# Okay, so this guy uses our big long list of terminal sequences.
	# The trick is to keep calling it until you get a result that
	# isn't None (or NoKeyPressed, if blocking is False).
	# The end result is either a bytes object representing the bare
	# key pressed, or a frozenset (such as frozenset({'f2', 'ctrl',
	# 'shift'}) representing the special key pressed.
	@classmethod
	def getkey_advanced(cls, interruptable=True):
		if cls.advanced_lut is None:
			cls.advanced_lut = generate_terminal_code_lut()[0]
		if cls.advanced_pos is None:
			cls.advanced_pos = cls.advanced_lut
		key = cls.getkey(interruptable)
		if key not in cls.advanced_pos:
			cls.advanced_pos = None
			return key
		else:
			cls.advanced_pos = cls.advanced_pos[key]
			if not isinstance(cls.advanced_pos, dict):
				ret = cls.advanced_pos
				cls.advanced_pos = None
				return ret
	# Changes whether or not performing a read on STDIN blocks.
	# Call with True for blocking behavior (default)
	# Call with False for nonblocking behavior.
	@classmethod
	def setblocking(cls, blocking):
		if blocking:
			cls.fl = cls.fl & ~os.O_NONBLOCK
		else:
			cls.fl = cls.fl | os.O_NONBLOCK
		fcntl.fcntl(cls.fd, fcntl.F_SETFL, cls.fl)
	@classmethod
	def getblocking(cls):
		return not cls.fl & os.O_NONBLOCK > 0
	@classmethod
	def clearLine(cls, flush=True):
		import jlib
		sys.stderr.write(jlib.encapsulate_ansi('erase_line'))
		sys.stderr.write(jlib.encapsulate_ansi('cursor_horizontal_absolute', ['1']))
		if flush:
			sys.stderr.flush()

	# originally from stackoverflow.com
	# Poll the controlling terminal for its dimensions.
	# This gets called automatically if the sigwinch hook is installed.
	@classmethod
	def getSize(cls):
		def ioctl_GWINSZ(fd):
			try:
				import fcntl, termios, struct, os
				cr = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234'))
			except:
				return None
			return cr
		cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
		if not cr:
			try:
				fd = os.open(os.ctermid(), os.O_RDONLY)
				cr = ioctl_GWINSZ(fd)
				os.close(fd)
			except:
				pass
		if not cr:
			try:
				cr = (env['LINES'], env['COLUMNS'])
			except:
				cr = (25, 80)
		cls.size = (int(cr[1]), int(cr[0]))
		return int(cr[1]), int(cr[0])
	# Vestigal, I believe...
	@classmethod
	def sizeChanged(cls):
		if _sizeChanged:
			_sizeChanged = False
			return True
		return False
	@classmethod
	def clear(cls, flush=True):
		import jlib
		sys.stderr.buffer.write(jlib.encapsulate_ansi('erase_screen').encode())
		if flush:
			sys.stderr.buffer.flush()
	@classmethod
	def clearScrollback(cls, flush=True):
		import jlib
		sys.stderr.buffer.write(jlib.encapsulate_ansi('erase_screen_and_scrollback').encode())
		if flush:
			sys.stderr.buffer.flush()
# }}}

def formatLine(txt, maxWidth, justify="left", moreString="$"):# {{{
	# TODO: Figure out a way to account for tab width when sizing,
	# but print tab characters instead of spaces.
	# Problems arise when tab characters occur in the slice,
	# so we just expand them.
	# I think this strip() is causing size to be misreported, causing line overflow.
	#newTxt = str(txt).strip().expandtabs()
	# Ok, converting to a string makes unicode cry.
	#newTxt = str(txt).expandtabs()
	newTxt = txt.expandtabs()
	if len(stripAnsi(newTxt)) > maxWidth:
		maxWidth -= len(moreString)
		while len(stripAnsi(newTxt)) > maxWidth:
			newTxt = newTxt[:-1]
		
		if justify == "left":
			return "{}{}".format(newTxt, moreString)
		elif justify == "right":
			return "{}{}".format(moreString, newTxt)
		else:
			raise ValueError('only "left" and "right" are valid arguments for the justify argument')

	return txt
		# }}}
class DumLock:# {{{
	def __init__(self):
		pass
	def acquire(self):
		pass
	def release(self):
		pass
# }}}
# TODO: signal handling interrupts sleep
# TODO: signal handling probably just fucked threads. :( 
# http://docs.python.org/library/signal


################################################################################
#print "Installing sigwinch hook"

class DumbWriter(object):# {{{
	def __init__(self, outfile):
		self.outfile = outfile
	def write(self, data):
		try:
			self.outfile.write(data)
		except IOError:
			pass
	def flush(self):
		try:
			self.outfile.flush()
		except IOError:
			pass
# }}}
class TeeWriter(object):# {{{
	def __init__(self, filename):
		self.filename = filename
		self.fh = open(self.filename, "w")
	def write(self, data):
		sys.stdout.write(data)
		self.fh.write(data)
	def flush(self):
		sys.stdout.flush()
# }}}
class DotPrinterSlots(object):
	dotfile=DumbWriter(sys.stderr)
	printfile=sys.stdout
	activeidx = None
	slots = []
	lockobj = None
	init_complete = False
	preferred_slot = None
	@classmethod
	def init(cls):
		if not cls.init_complete:
			Term.init()
			Term.disableCursor()
			cls.init_complete = True
	@classmethod
	def lock(cls):
		if cls.lockobj is not None:
			cls.lockobj.acquire()
	@classmethod
	def release(cls):
		if cls.preferred_slot is not None:
			cls.setActive(cls.preferred_slot)
		if cls.lockobj is not None:
			cls.lockobj.release()
	@classmethod
	def len(cls):
		return len(cls.slots)
	@classmethod
	def register(cls, dp, after=None, before=None):
		cls.init()
		if len(cls.slots) > 0:
			cls.setActive(cls.slots[0])
		if after is not None:
			idx = cls.slots.index(after)
			cls.slots.insert(idx + 1, dp)
		elif before is not None:
			idx = cls.slots.index(before)
			cls.slots.insert(idx, dp)
		else:
			cls.slots.append(dp)
		cls.refresh()
	@classmethod
	def deregister(cls, dp, msg):
		import jlib
		if cls.preferred_slot == dp:
			cls.preferred_slot = None
		if dp not in cls.slots:
			return
		if msg is not None:
			cls.line(msg)
		if len(cls.slots) > 0:
			for i in range(len(cls.slots)):
				cls.setActive(cls.slots[i])
				cls.dotfile.write(jlib.encapsulate_ansi('erase_line') + jlib.encapsulate_ansi('cursor_horizontal_absolute', ['1']))
			cls.setActive(cls.slots[0])
		cls.slots.remove(dp)
		#else:
			#cls.dotfile.write(jlib.encapsulate_ansi('erase_line') + jlib.encapsulate_ansi('cursor_horizontal_absolute', ['1']))
			#cls.dotfile.write("\n")
			#cls.refresh()
		cls.dotfile.flush()
		cls.printfile.flush()
		cls.refresh()
	@classmethod
	def refresh(cls):
		refresh_flush = True
		if cls.preferred_slot is not None:
			refresh_flush = False
		first = True
		for x in cls.slots:
			if first:
				first = False
			else:
				cls.dotfile.write("\n")
			x.refresh(activate=False, flush=refresh_flush)
		if len(cls.slots) > 0:
			cls.activeidx = len(cls.slots) - 1
		if cls.preferred_slot is not None:
			cls.setActive(cls.preferred_slot)
	@classmethod
	def setActive(cls, dp):
		import jlib
		if cls.slots[cls.activeidx] == dp:
			# Quick shortcircuit if we're already the active slot.
			return
		if hasattr(cls.slots[cls.activeidx], 'deactivation_cb'):
			cls.slots[cls.activeidx].deactivation_cb()
		curridx = cls.activeidx
		cls.activeidx = cls.slots.index(dp)
		delta = cls.activeidx - curridx
		if delta < 0:
			cls.dotfile.write(jlib.encapsulate_ansi('cursor_up', ["{}".format(abs(delta))]))
		elif delta > 0:
			cls.dotfile.write(jlib.encapsulate_ansi('cursor_down', ["{}".format(delta)]))
		if hasattr(dp, 'activation_cb'):
			dp.activation_cb()
	@classmethod
	def clear(cls):
		import jlib
		cls.setActive(cls.slots[0])
		cls.dotfile.write(jlib.encapsulate_ansi('erase_screen') + jlib.encapsulate_ansi('cursor_position', ['1', '1']))
		cls.refresh()
	@classmethod
	def line(cls, *values, sep=' ', end='', file=None, printfile=True, **kwargs):
		"""\
		Generates a line of text which is printed above the stack, and will
		scroll in a manner that can be expected.

		Some s(tupid|mart) stdout/stderr alternation trickery is employed so
		that only the supplied message text is written to stdout, while
		control characters and stack redraw occurs on stderr. This way,
		applications can still reliably be redirected. If you do not want
		the message text to be sent to stdout, set the 'printfile' parameter
		to False.

		Note that this function is designed so that it's supposed to more-or-less
		"do the right thing" if you replace your standard `print` statement with
		it (or one of it's slot-based children), like:

		global print
		orig_print = print
		print = JaysTerm.DotPrinterSlots.line

		"""
		import jlib
		values = [ x if type(x) in StringTypes else str(x) for x in values ]
		msg = sep.join(values)
		# Make sure "file" goes to where it's supposed to go, if it's not
		# stdout or stderr.
		if file is not None and file is not sys.stdout and file is not sys.stderr:
			file.write(msg + "\n")
			return
		if printfile:
			print_fh = cls.printfile
		else:
			print_fh = cls.dotfile
		# go to the top of the stack
		if len(cls.slots) > 0:
			cls.setActive(cls.slots[0])
		# on "stderr", erase line, move cursor to line start, flush
		cls.dotfile.write(jlib.encapsulate_ansi('erase_line') + jlib.encapsulate_ansi('cursor_horizontal_absolute', ['1']))
		cls.dotfile.flush()
		# on "stdout", write our line (but don't move to the next just yet), flush
		print_fh.write(msg)
		# Funny little workaround
		while True:
			try:
				print_fh.flush()
				break
			except IOError:
				pass
		# on "stderr", erase the rest of the line, flush
		cls.dotfile.write(jlib.encapsulate_ansi('erase_line_from_cursor'))
		cls.dotfile.flush()
		# on "stdout", advance to the next line, flush
		print_fh.write("\n")
		print_fh.flush()
		# redraw the stack
		cls.refresh()

class FakeUpdatingLine:
	def __init__(self, silent=False):
		self.silent = silent
	def update(self, txt=None, flush=None):
		pass
	def line(self, *values, **kwargs):
		if not self.silent:
			print(*values, **kwargs)
	def close(self, msg=None):
		pass

class UpdatingLine:
	# Note: This can be instantiated or just used in-place.
	# If you instantiate an UpdatingLine object, it will install the SIGWINCH hook for you.
	# If you just use this as a classmethod in-place, be sure to call UpdatingLine.init(),
	# or else shit will NOT work right, and you're gonna have a bad time.
	buf = ""
	justify = "left"
	moreString = "$"


	def __init__(self, update=None, line=None, justify=None, moreString=None, after=None, before=None, clear_on_close=True):
		self.closed = False
		self.dotfile = DotPrinterSlots.dotfile
		self.printfile = DotPrinterSlots.printfile
		DotPrinterSlots.lock()
		DotPrinterSlots.register(self, after=after, before=before)
		DotPrinterSlots.release()
		self.clear_on_close = clear_on_close
		if line is not None:
			self.line(line)
		if update is not None:
			self.update(update)

	def getJustify(self):
		return self.justify
	def setJustify(self, x):
		self.justify = x
	def getMoreString(self):
		return self.moreString
	def setMoreString(self, x):
		self.moreString = x
	def getBuf(self):
		return self.buf
	def refresh(self, activate=True, flush=True):
		import jlib
		if self.closed:
			return
		if activate:
			DotPrinterSlots.setActive(self)
		colSize = Term.size[0]
		#newTxt = formatLine(self.buf, colSize, self.justify, self.moreString)
		self.dotfile.write(jlib.encapsulate_ansi('erase_line') + jlib.encapsulate_ansi('cursor_horizontal_absolute', ['1']) + jlib.encapsulate_ansi('disable_line_wrap'))
		#self.dotfile.write(newTxt)
		self.dotfile.write(self.buf)
		self.dotfile.write(jlib.encapsulate_ansi('enable_line_wrap') + jlib.encapsulate_ansi('color', [jlib.ansi_colors['normal']]))
		if flush:
			self.dotfile.flush()
	def update(self, txt=None, flush=True):
		import jlib
		if self.closed:
			return
		DotPrinterSlots.lock()
		DotPrinterSlots.setActive(self)
		colSize = Term.size[0]
		if txt is None:
			txt = self.buf
		lastLineLen = 0
		self.dotfile.write(jlib.encapsulate_ansi('erase_line') + jlib.encapsulate_ansi('cursor_horizontal_absolute', ['1']) + jlib.encapsulate_ansi('disable_line_wrap'))
		self.dotfile.write(txt)
		self.dotfile.write(jlib.encapsulate_ansi('enable_line_wrap') + jlib.encapsulate_ansi('color', [jlib.ansi_colors['normal']]))
		self.dotfile.write(jlib.encapsulate_ansi('cursor_horizontal_absolute', ["1"]))
		if flush:
			self.dotfile.flush()
		self.buf = txt
		DotPrinterSlots.release()
	def line(self, *values, sep=' ', end='', file=None, printfile=True, **kwargs):
		if self.closed:
			return
		DotPrinterSlots.lock()
		DotPrinterSlots.line(*values, sep=sep, end=end, file=file, printfile=printfile)
		DotPrinterSlots.release()
	def clear(self):
		if self.closed:
			return
		DotPrinterSlots.lock()
		DotPrinterSlots.clear()
		DotPrinterSlots.release()
	def close(self, msg=None):
		if self.closed:
			return
		DotPrinterSlots.lock()
		if msg is True:
			msg = self.buf
		elif msg is None:
			if not self.clear_on_close:
				msg = self.buf
		DotPrinterSlots.deregister(self, msg)
		DotPrinterSlots.release()
		self.closed = True
	def __del__(self):
		# This little "if" clause is here to prevent
		# "ImportError: sys.meta_path is None, Python is likely shutting down"
		# messages in multiprocessing environments.
		if sys.meta_path is not None:
			self.close()

_DOT='▒'
_DOT_EIGHTHS = ['▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']

class DotPrinter(object):
	def __init__(self, maxcount, showcount=False, label=None, afterlabel=None, countjustify=0, grouping=True, dotchar=_DOT, frac_dots=True, frac_dotchars=_DOT_EIGHTHS, colors=True, clear_on_close=False):
		locale.setlocale(locale.LC_ALL, locale.getdefaultlocale())
		# currcount is used to track our progress.
		self.currcount = 0
		# dotsprinted represents literally how many "dot" characters
		# we've printed.
		self.dotsprinted = 0
		# maxcount is the number that indicates our end goal.
		self.maxcount = maxcount
		# when showcount is True, numeric progress indication
		# ("<currcount>/<maxcount>") is also displayed.
		self.showcount = showcount
		# Label is also displayed if not None.
		self.label = label
		self.afterlabel = afterlabel
		# The count display is justified to this many characters.
		self.countjustify = countjustify
		# If grouping is True, commas are put in the count display.
		self.grouping = grouping
		self.dotfile = DotPrinterSlots.dotfile
		self.printfile = DotPrinterSlots.printfile
		# This is the character that represents a dot!
		self.dotchar = dotchar
		# If frac_dots is True, fractions of a dot are used.
		self.frac_dots = frac_dots
		# These are the characters that represent fractions of a dot.
		self.frac_dotchars = frac_dotchars
		self.frac_dot_qty = len(frac_dotchars)
		self.colors = colors
		self.clear_on_close = clear_on_close
		DotPrinterSlots.lock()
		DotPrinterSlots.register(self)
		DotPrinterSlots.release()
		if self.colors:
			import jlib
			fab = jlib.get_fabulous(force=True)
			if 'fgtrue' in fab:
				self.fgfunc = fab['fgtrue']
			else:
				self.fgfunc = fab['fg256']
	def refresh(self, activate=True, flush=True):
		import jlib
		if activate:
			DotPrinterSlots.setActive(self)
		#    1/1024 whatever.h [                                   ]
		cols, rows = Term.size
		self.dotstart = 1
		self.dotend = cols
		if self.afterlabel is not None:
			labelsize = len(" {}".format(self.afterlabel))
			self.dotend -= labelsize

		self.dotfile.write(jlib.encapsulate_ansi('erase_line') + jlib.encapsulate_ansi('cursor_horizontal_absolute', ['1']) + jlib.encapsulate_ansi('disable_line_wrap'))
		if self.showcount:
			maxcount_len = len(("{:n}" if self.grouping else "{}").format(self.maxcount))
			if self.countjustify is not None and maxcount_len < self.countjustify:
				maxcount_len = self.countjustify
			# maxcount_len + '/' + maxcount_len + ' '
			countsize = (maxcount_len * 2) + 2
			self.maxcountsize = maxcount_len
			self.countstart = self.dotstart
			self.dotstart += countsize
			self.dotfile.write(("{:n}" if self.grouping else "{}").format(self.currcount).rjust(self.maxcountsize, ' ') + '/' + ("{:n}" if self.grouping else "{}").format(self.maxcount).rjust(self.maxcountsize, ' ') + ' ')

		if self.label is not None:
			labelsize = len("{} ".format(self.label))
			self.dotstart += labelsize
			self.dotfile.write(self.label + ' ')
		if self.afterlabel is not None:
			self.dotfile.write(jlib.encapsulate_ansi('cursor_horizontal_absolute', ["{}".format(self.dotend + 1)]) + ' ' + self.afterlabel)
		self.dotstoprint = self.dotend - self.dotstart - 1
		if self.dotstoprint == 0:
			# cop-out zero-div mitigation
			self.dotstoprint += 1
		if self.colors:
			import colorsys
			color_step = 1 / self.dotstoprint
			def colorcalc(frac):
				s_thresh = 0.83333333333333333333
				h = frac
				s = 1.0
				if frac >= s_thresh:
					s = 1.0 - ((frac - s_thresh) / (1.0 - s_thresh))
				v = 1.0
				fgc = '#' + ''.join([ "{:02x}".format(x) for x in [ x if x <= 255 else 255 for x in [ int(x * 255) for x in colorsys.hsv_to_rgb(h, s, v) ] ] ])
				return fgc
		if self.maxcount < self.dotstoprint:
			self.dotstoprint = self.maxcount
			self.dotend = self.dotstart + self.dotstoprint + 1
		if self.dotstoprint > 0:
			self.dotfile.write('[')
			self.dotfile.write(jlib.encapsulate_ansi('cursor_horizontal_absolute', ["{}".format(self.dotend)]))
			self.dotfile.write(']')
			self.dotfile.write(jlib.encapsulate_ansi('cursor_horizontal_absolute', ["{}".format(self.dotstart + 1)]))
			self.itemsperdot = (float(self.maxcount) / float(self.dotstoprint))
			dotnum = int(self.currcount / self.itemsperdot)
			self.dotsprinted = 0
			self.frac_dot_printed = 0

			while dotnum > self.dotsprinted:

				if self.frac_dots:
					to_print = self.frac_dotchars[-1]
				else:
					to_print = self.frac_dotchars[self.dotchar]
				if self.colors:
					fgc = colorcalc(self.dotsprinted * color_step)
					self.dotfile.write(str(self.fgfunc(fgc, to_print)))
				else:
					self.dotfile.write(to_print)
				self.dotsprinted += 1
			if self.frac_dots:
				dot_remainder = self.currcount % self.itemsperdot
				# Note: this is represented as an index into self.frac_dotchars. -1 means "None printed yet/Nothing to print"
				self.frac_dot_printed = int((dot_remainder / self.itemsperdot) * self.frac_dot_qty) - 1
				if self.frac_dot_printed > -1:
					if self.colors:
						fgc = colorcalc(self.dotsprinted * color_step)
						self.dotfile.write(str(self.fgfunc(fgc, self.frac_dotchars[self.frac_dot_printed])))
					else:
						self.dotfile.write(self.frac_dotchars[self.frac_dot_printed])
		self.dotfile.write(jlib.encapsulate_ansi('enable_line_wrap'))
		if flush:
			self.dotfile.flush()
	def update(self, newcount, flush=True):
		DotPrinterSlots.lock()
		DotPrinterSlots.setActive(self)
		self.currcount = newcount
		self.refresh()
		#if self.dotstoprint > 0:
		#	dotnum = int(self.currcount / self.itemsperdot)
		#	if self.frac_dots:
		#		dot_remainder = self.currcount % self.itemsperdot
		#		new_frac_dot_printed = int((dot_remainder / self.itemsperdot) * self.frac_dot_qty) - 1
		#	if dotnum > self.dotsprinted:
		#		self.dotfile.write(encapsulate_ansi('disable_line_wrap'))
		#		self.dotfile.write(encapsulate_ansi('cursor_horizontal_absolute', ["{}".format(self.dotstart + 1 + self.dotsprinted)]))
		#		while dotnum > self.dotsprinted:
		#			if self.frac_dots:
		#				self.dotfile.write(self.frac_dotchars[-1])
		#			else:
		#				self.dotfile.write(self.dotchar)
		#			self.dotsprinted += 1
		#		self.frac_dot_printed = new_frac_dot_printed
		#		if self.frac_dot_printed > -1:
		#			self.dotfile.write(self.frac_dotchars[self.frac_dot_printed])
		#		self.dotfile.write(encapsulate_ansi('enable_line_wrap'))
		#	elif self.frac_dot_printed != new_frac_dot_printed:
		#		self.dotfile.write(encapsulate_ansi('disable_line_wrap'))
		#		self.dotfile.write(encapsulate_ansi('cursor_horizontal_absolute', ["{}".format(self.dotstart + 1 + self.dotsprinted)]))
		#		self.frac_dot_printed = new_frac_dot_printed
		#		if self.frac_dot_printed > -1:
		#			self.dotfile.write(self.frac_dotchars[self.frac_dot_printed])
		#if self.showcount:
		#	self.dotfile.write(encapsulate_ansi('cursor_horizontal_absolute', ["{}".format(self.countstart)]))
		#	self.dotfile.write(("{:n}" if self.grouping else "{}").format(self.currcount).rjust(self.maxcountsize, ' '))
		#self.dotfile.write(encapsulate_ansi('cursor_horizontal_absolute', ["1"]))
		#if flush:
		#	self.dotfile.flush()
		DotPrinterSlots.release()
	def line(self, *values, sep=' ', end='', file=None, printfile=True, **kwargs):
		DotPrinterSlots.line(*values, sep=sep, end=end, file=file, printfile=printfile)
	def close(self, printlabel=True, text=None):
		DotPrinterSlots.lock()
		if not self.clear_on_close:
			if printlabel:
				msg = StringIO()
				if self.showcount:
					maxcount_len = len(("{:n}" if self.grouping else "{}").format(self.maxcount))
					if self.countjustify is not None and maxcount_len < self.countjustify:
						maxcount_len = self.countjustify
					# maxcount_len + '/' + maxcount_len + ' '
					countsize = (maxcount_len * 2) + 2
					self.maxcountsize = maxcount_len
					self.countstart = self.dotstart
					self.dotstart += countsize
					msg.write(("{:n}" if self.grouping else "{}").format(self.currcount).rjust(self.maxcountsize, ' ') + ' ')
				if self.label is not None:
					msg.write(self.label)
				text = msg.getvalue()
		DotPrinterSlots.deregister(self, text) 
		DotPrinterSlots.release()
	def activation_cb(self):
		import jlib
		self.dotfile.write(jlib.encapsulate_ansi('cursor_horizontal_absolute', ["{}".format(self.dotstart + 1 + self.dotsprinted)]))
	def __del__(self):
		if sys.meta_path is not None:
			self.close()

# Note: You may be tempted to wrap EditingLine.poll() around a select() or
# poll() object in order to cut down on busy sleeps... be sure to call
# the EditingLine instance's poll() object at least once beforehand, in order
# to set the terminal in the right state.  Example:
#if __name__ == '__main__':
#	Term.init()
#	import select
#	p = select.poll()
#	p.register(sys.stdin.fileno(), select.POLLIN)
#	l = EditingLine(history=['poop', 'shit', 'crappola'])
#	l.poll()
#	keepGoing = True
#	while keepGoing:
#		resp = p.poll(1000)
#		for fd, typ in resp:
#			if fd == sys.stdin.fileno():
#				resp2 = l.poll()
#				if (resp2):
#					msg = l.getBuf()
#					l.close(msg)
#					keepGoing = False
#					break

def count_significant_bits(byte):
	count = 0
	for x in reversed(range(8)):
		if byte & (1 << x):
			count += 1
		else:
			break
	return count

# Terminal-y input sequences:
# (I'm lazy and don't want to build this out by hand, so we'll
# parse it out if/when we need it...)

# Note: some keys are missing from this list. This is purely because
# X11 intercepts them in my current config:
# * f11
# * ctrl + f1
# * ctrl + f2
# * ctrl + f8
# * ctrl + f12
terminal_sequences = """
* ESC [ A — up arrow
* ESC [ B — down arrow
* ESC [ C — right arrow
* ESC [ D — left arrow
* ESC [ H — home
* ESC [ F — end

* ESC [ 2 ~ — insert
* ESC [ 3 ~ — delete
* ESC [ 5 ~ — page up
* ESC [ 6 ~ — page down
* ESC [ 3 ; 2 ~ — shift + delete
* ESC [ 3 ; 5 ~ —  ctrl + delete
* ESC [ 5 ; 5 ~ —  ctrl + page up
* ESC [ 6 ; 5 ~ —  ctrl + page down

* ESC [ 1 ; 2 A — shift + up arrow
* ESC [ 1 ; 2 B — shift + down arrow
* ESC [ 1 ; 2 C — shift + right arrow
* ESC [ 1 ; 2 D — shift + left arrow
* ESC [ 1 ; 3 A —  alt  + up arrow
* ESC [ 1 ; 3 B —  alt  + down arrow
* ESC [ 1 ; 3 C —  alt  + right arrow
* ESC [ 1 ; 3 D —  alt  + left arrow
* ESC [ 1 ; 4 A — shift +  alt  + up arrow
* ESC [ 1 ; 4 B — shift +  alt  + down arrow
* ESC [ 1 ; 4 C — shift +  alt  + right arrow
* ESC [ 1 ; 4 D — shift +  alt  + left arrow
* ESC [ 1 ; 5 A —  ctrl + up arrow
* ESC [ 1 ; 5 B —  ctrl + down arrow
* ESC [ 1 ; 5 C —  ctrl + right arrow
* ESC [ 1 ; 5 D —  ctrl + left arrow
* ESC [ 1 ; 6 A — shift +  ctrl + up arrow
* ESC [ 1 ; 6 B — shift +  ctrl + down arrow
* ESC [ 1 ; 6 C — shift +  ctrl + right arrow
* ESC [ 1 ; 6 D — shift +  ctrrl + left arrow
* ESC [ 1 ; 7 C —  ctrl +  alt  + right arrow
* ESC [ 1 ; 7 D —  ctrl +  alt  + left arrow
* ESC [ 1 ; 8 C — shift +  ctrl +  alt + right arrow
* ESC [ 1 ; 8 C — shift +  ctrl +  alt + left arrow
* ESC [ 1 ; 3 H —  alt  + home
* ESC [ 1 ; 3 F —  alt  + end
* ESC [ 1 ; 5 H — shift +  home
* ESC [ 1 ; 5 F — shift +  end
* ESC [ 1 ; 7 H —  ctrl +  alt  + end
* ESC [ 1 ; 7 F —  ctrl +  alt  + end

* ESC O P — f1   
* ESC O Q — f2
* ESC O R — f3
* ESC O S — f4
* ESC [ 1 5 ~ — f5
* ESC [ 1 7 ~ — f6
* ESC [ 1 8 ~ — f7
* ESC [ 1 9 ~ — f8
* ESC [ 2 0 ~ — f9
* ESC [ 2 1 ~ — f10
* ESC [ 2 4 ~ — f12
* ESC [ 1 ; 2 P — shift + f1
* ESC [ 1 ; 2 Q — shift + f2
* ESC [ 1 ; 2 R — shift + f3
* ESC [ 1 ; 2 S — shift + f4
* ESC [ 1 5 ; 2 ~ — shift + f5
* ESC [ 1 7 ; 2 ~ — shift + f6
* ESC [ 1 8 ; 2 ~ — shift + f7
* ESC [ 1 9 ; 2 ~ — shift + f8
* ESC [ 2 0 ; 2 ~ — shift + f9
* ESC [ 2 3 ; 2 ~ — shift + f11
* ESC [ 2 4 ; 2 ~ — shift + f12
* ESC [ 1 ; 5 R — ctrl + f3
* ESC [ 1 ; 5 S — ctrl + f4
* ESC [ 1 5 ; 5 ~ — ctrl + f5
* ESC [ 1 7 ; 5 ~ — ctrl + f6
* ESC [ 1 8 ; 5 ~ — ctrl + f7
* ESC [ 2 0 ; 5 ~ — ctrl + f9
* ESC [ 2 1 ; 5 ~ — ctrl + f10
* ESC [ 2 3 ; 5 ~ — ctrl + f11
* ESC [ 1 ; 6 P — shift +  ctrl + f1
* ESC [ 1 ; 6 Q — shift +  ctrl + f2
* ESC [ 1 ; 6 R — shift +  ctrl + f3
* ESC [ 1 ; 6 S — shift +  ctrl + f4
* ESC [ 1 5 ; 6 ~ — shift +  ctrl + f5
* ESC [ 1 7 ; 6 ~ — shift +  ctrl + f6
* ESC [ 1 8 ; 6 ~ — shift +  ctrl + f7
* ESC [ 1 9 ; 6 ~ — shift +  ctrl + f8
* ESC [ 2 0 ; 6 ~ — shift +  ctrl + f9
* ESC [ 2 1 ; 6 ~ — shift +  ctrl + f10
* ESC [ 2 3 ; 6 ~ — shift +  ctrl + f11
* ESC [ 2 4 ; 6 ~ — shift +  ctrl + f12
* ESC [ 1 ; 8 P — shift +  ctrl +  alt  + f1
* ESC [ 1 ; 8 Q — shift +  ctrl +  alt  + f2
* ESC [ 1 ; 8 R — shift +  ctrl +  alt  + f3
* ESC [ 1 ; 8 S — shift +  ctrl +  alt  + f4
* ESC [ 1 5 ; 8 ~ — shift +  ctrl +  alt  + f5
* ESC [ 1 7 ; 8 ~ — shift +  ctrl +  alt  + f6
* ESC [ 1 8 ; 8 ~ — shift +  ctrl +  alt  + f7
* ESC [ 1 9 ; 8 ~ — shift +  ctrl +  alt  + f8
* ESC [ 2 0 ; 8 ~ — shift +  ctrl +  alt  + f9
* ESC [ 2 1 ; 8 ~ — shift +  ctrl +  alt  + f10
* ESC [ 2 3 ; 8 ~ — shift +  ctrl +  alt  + f11
* ESC [ 2 4 ; 8 ~ — shift +  ctrl +  alt  + f12
"""

def generate_terminal_code_lut():
	treelut = {}
	lut = {}
	lines = [ x.strip() for x in terminal_sequences.splitlines() if len(x.strip()) > 0 ]
	for line in lines:
		sequence, key = line.split('—')
		# Convert the right hand side into a key sequence
		keyspressed = frozenset([ x.strip() for x in key.split('+') ])
		# Integrate the left hand side into the lookup table...
		frags = [ x.encode() for x in sequence.split() ]
		# Drop the leading '*'
		if frags[0] == b'*':
			frags.pop(0)
		# Convert 'ESC' to an actual escape
		frags = [ b'\x1b' if x == b'ESC' else x for x in frags ]
		branch = treelut
		buf = b''
		while len(frags) > 0:
			frag = frags.pop(0)
			buf += frag
			if len(frags) > 0:
				if frag not in branch:
					branch[frag] = {}
				branch = branch[frag]
			else:
				branch[frag] = keyspressed
		lut[buf] = keyspressed
	return [treelut, lut]

# * ESC <just about any character> -- alt + character
#   * Yes, this DOES mean "alt + [, A" is the same as hitting the up arrow.

class CursorPosition:
	def __init__(self, row, col):
		self.row = row
		self.col = col
	@classmethod
	def from_match(cls, mat):
		return cls(row=int(mat.group('row')), col=int(mat.group('col')))
	def __repr__(self):
		return "<CursorPosition row:{} col:{}>".format(self.row, self.col)

class TerminalSequenceParser:
	"""
	This thing makes a somewhat competent attempt to handle terminal input.

	Instantiate it, and feed your key data to it, as binary bytes() data,
	one character at a time.

	What you'll get back depends on the internal state:

	* None — the parser encountered an escape character and is currently working voodoo.
	       Continue to feed it characters until it comes back with something else, or
		   call the abort() method to push the proverbial coin return button.
	* bytes — if the parser couldn't figure out anything special to do with your input,
	       it will return it as a bytes() object. Most of the time, you'll get a single
		   character back, but expect multiple if the parser gave up.
	* frozenset — anything parsed out of the terminal_sequences heap will get returned
	       as a frozenset.
	* something else — Special cases, such as the response to a "cursor position" request
	       will get returned as some sort of object.
	"""
	def __init__(self):
		import re
		self.lut = generate_terminal_code_lut()[1]
		# Note: Request cursor position by issuing "\x1b[?6n", not "\x1b[6n", as the reply from the latter
		# command can mimic ctrl+f3 in certain cases.
		self.patterns = [
			[re.compile(b"^\x1b\[\?(?P<row>\d+);(?P<col>\d+);1R$"), lambda x: CursorPosition.from_match(x)],
		]
		self.buf = b''
	def feed(self, char):
		ret = char
		if len(self.buf) < 1:
			if char == b"\x1b":
				self.buf += char
				ret = None
		else:
			ret = None
			self.buf += char
			charval = ord(char)
			if charval >= 48 and charval <= 57:
				pass
			elif char in b';[?':
				pass
			else:
				ret = self.buf
				self.buf = b''
		if ret is not None and len(ret) > 1:
			if ret in self.lut:
				ret = self.lut[ret]
			else:
				for pat, act in self.patterns:
					mat = pat.search(ret)
					if mat:
						ret = act(mat)
		return ret
		


class EditingLine(object):
	# Implementation notes:
	# Internal buffers (escbuf, utf8buf, lastbyte, lastpoll) are bytes objects,
	# as we need to retain and interpret escape characters, utf-8 fragments, and
	# the like. The history list, however, consists of strings, because we need
	# to calculate lengths in terms of printable characters... and at the end
	# of the day, that's also what the user cares about and expects.
	def __init__(self, history=[], prompt=''):
		# This regex is used to cheese our ^W "kill last word" functionality...
		import re
		self.kill_word_pat = re.compile("^(.*\S)(\s+\S+\s*)$")

		self.dotfile = DotPrinterSlots.dotfile
		self.printfile = DotPrinterSlots.printfile
		Term.init()
		Term.raw()
		# Note to future self:
		# System is not happy AT ALL if you use the call that's commented out below.
		#Term.setblocking(False)

		# winscroll controls the granularity of how many characters a time
		# the "window" of the line we're editing jumps back and forth when
		# the size of the line exceeds the width of the display.
		self.winscroll = 10
		# Where in the line the cursor is currently located.
		self.cursorpos = 0
		# How many characters forward the start of the window is currently positioned.
		self.linewin = 0
		# Line editing history.
		self.history = history
		# The prompt is displayed before the start of the line.
		self.prompt = prompt
		if len(self.history) > 0 and self.history[-1] == '':
			pass
		else:
			self.history.append('')
		self.historypos = len(self.history) - 1
		DotPrinterSlots.lock()
		DotPrinterSlots.register(self)
		DotPrinterSlots.preferred_slot = self
		DotPrinterSlots.release()
		self.reset(history)
		self.activation_cb()
		#self.debugline = JaysTerm.UpdatingLine()
	def reset(self, history=[], prompt=None):
		self.history = history
		if prompt is not None:
			self.prompt = prompt
		if len(self.history) > 0 and self.history[-1] == '':
			pass
		else:
			self.history.append('')
		# The index of the line currently visible / being edited.
		self.historypos = len(self.history) - 1
		# This flag is set to indicate that we've received an escape byte,
		# and are currently in the process of interpreting an escape sequence.
		self.escmode = False
		# bytes received while escmode is set are stored here until we have
		# enough of them to interpret the sequence.
		self.escbuf = b''	
		self.cursorpos = 0
		self.linewin = 0
		# counter used when receiving a utf-8 character to track how many
		# additional bytes we're expecting to see.
		self.utf8bytesleft = 0
		# bytes obtained while receiving a utf-8 character are stored here
		# for safekeeping.
		self.utf8buf = b''
		# Stores the last byte retrieved from stdin.
		# If poll() is called with process_all_input set to False, this can
		# be interrogated afterwards and you will be guaranteed to get hold of
		# each individual byte.
		self.lastbyte = b'\x00'
		self.lastpoll = b''
		self.refresh()
	def getBuf(self):
		return self.history[self.historypos]
	def position_cursor(self):
		import jlib
		# Note: module "colors" is provided by the "ansicolors" package in pip.
		import colors, wcwidth
		self.dotfile.write(jlib.encapsulate_ansi('cursor_horizontal_absolute', [str(len(colors.strip_color(self.prompt)) + wcwidth.wcswidth(self.history[self.historypos][:self.cursorpos]) - self.linewin + 1)]))
	def refresh(self, activate=True, flush=True):
		import jlib
		# Note: module "colors" is provided by the "ansicolors" package in pip.
		self.activation_cb()
		import colors
		colSize = Term.size[0]
		if activate:
			DotPrinterSlots.setActive(self)

		# Clear the line 
		self.dotfile.write(jlib.encapsulate_ansi('erase_line') + jlib.encapsulate_ansi('cursor_horizontal_absolute', ['1']))
		# If the cursor position is to the left of the visible window,
		# jump the window back in <winscroll>-sized chunks until we reach
		# the cursor position.
		while self.cursorpos < self.linewin:
			self.linewin -= self.winscroll
			if self.linewin < 0:
				self.linewin = 0
		# If the cursor position is to the right of the visible window,
		# jump the window forward.
		while self.cursorpos > self.linewin + (colSize - len(colors.strip_color(self.prompt))):
			self.linewin += self.winscroll
		self.dotfile.write(self.prompt + self.history[self.historypos][self.linewin:self.linewin + (colSize - len(colors.strip_color(self.prompt)))])
		self.position_cursor()
		if flush:
			self.dotfile.flush()
		#DotPrinterSlots.release()
	def poll(self, process_all_input=True):
		"""
		Uses select.select() to determine readability of sys.stdin, and, if
		true, calls Term.getkey() one or more times to retrieve and interpret
		the user's input. Returns True if the user hit enter, indicating that
		it's now time for you to call getbuf() to retrieve the culmination of
		the user's efforts, and then perhaps reset() to prepare the next
		iteration of the line editing experience... otherwise it returns False.

		If process_all_input is set to False, this method will return after
		at most 1 byte is retrieved from stdin, allowing you to play along at
		home by checking self.lastbyte, otherwise additional data from stdin
		(if present) will be processed... unless, of course, a linefeed comes
		in.

		Note: if you ARE attempting to play along at home, keep in mind that
		poll() will come back and self.lastbyte will remain unchanged if there
		isn't any data to read in sys.stdin, so you'll want to prequalify
		whether or not you want to call poll() with your own calls to
		select.select() or the like.
		"""
		ifh, ofh, xfh = select.select([sys.stdin.fileno()], [], [], 0)
		keepGoing = len(ifh) > 0
		while keepGoing:
			DotPrinterSlots.lock()
			c = Term.getkey()
			DotPrinterSlots.release()
			self.lastbyte = c
			if self.escmode:
				if c == b'\x1b':
					self.escmode = False
					self.escbuf = b''
					# do something here
				else:
					self.escbuf += c
				if len(self.escbuf) > 1:
					if self.escbuf == b'[A': # up
						if self.historypos > 0:
							self.historypos -= 1
							self.cursorpos = len(self.history[self.historypos])
					elif self.escbuf == b'[B': # down
						if self.historypos < len(self.history) - 1:
							self.historypos += 1
							self.cursorpos = len(self.history[self.historypos])
					elif self.escbuf == b'[C': # right
						self.cursorpos += 1
					elif self.escbuf == b'[D': # left
						self.cursorpos -= 1
					elif self.escbuf == b'[H': # home
						self.cursorpos = 0
					elif self.escbuf == b'[F': # end
						self.cursorpos = len(self.history[self.historypos])
					if self.cursorpos < 0:
						self.cursorpos = 0
					if self.cursorpos > len(self.history[self.historypos]):
						self.cursorpos = len(self.history[self.historypos])
					self.escbuf = b''
					self.escmode = False
					self.refresh()
			else:
				# UTF-8 black magic fuckery.
				# Since we receive data from stdin one byte at a time, and
				# UTF-8 characters may consist of more than one byte, we need
				# some sort of provision to allow us to store intermediate
				# bytes until we have a complete character. This here is that
				# provision. Thankfully, due to the way that UTF-8 works, we
				# can simply count the number of consecutive significant bits
				# in each incoming byte, and if this number is greater than 1,
				# subtracting 1 from that number will tell us how many
				# additional bytes we need before that character is complete.
				self.utf8buf += c
				sigbits = count_significant_bits(ord(c))
				if self.utf8bytesleft > 0:
					self.utf8bytesleft -= 1
				elif sigbits > 1:
					self.utf8bytesleft = sigbits - 1
				if self.utf8bytesleft == 0:
					character = self.utf8buf.decode()
					self.utf8buf = b''
					# If we make any changes to the current line, we put the new
					# contents here. This allows us to consolidate the "changed
					# a line that isn't the last one in history? Make it a new
					# history item" logic.
					new_line = None
					# Handle escape character.
					if character == '\x1b':
						self.escmode = True
					# Handle backspace character.
					elif character == '\x7f':
						if self.cursorpos != 0:
							new_line = self.history[self.historypos][:self.cursorpos - 1] + self.history[self.historypos][self.cursorpos:]
							self.cursorpos -= 1
					# Handle "ctrl+a" -- move cursor to start of line.
					elif character == '\x01':
						self.cursorpos = 0
					# Handle "ctrl+d" -- end-of-file. Equivalent to CTRL+C,
					# but only if the current line is empty.
					elif character == '\x04':
						if len(self.history[self.historypos]) == 0:
							raise KeyboardInterrupt
					# Handle "ctrl+e" -- move cursor to end of line.
					elif character == '\x05':
						self.cursorpos = len(self.history[self.historypos])
					# Handle "ctrl+w" -- delete last word.
					elif character == '\x17':
						# Look at everything to the left of the cursor
						active = self.history[self.historypos][:self.cursorpos]
						mat = self.kill_word_pat.search(active)
						if mat:
							# If it matches our regex, then replace it with group 1
							new = mat.group(1)
						else:
							# If it doesn't match, replace it with nothing
							new = ''
						# Build updated line by combinding our altered stuff with everything to the right of the cursor
						new_line = new + self.history[self.historypos][self.cursorpos:]
						# Update cursor position.
						self.cursorpos = len(new)
					# Ignore linefeed character.
					elif character == '\x0a':
						return True
					# Note to myself: Why the holy hell did I have to add this in all of a sudden?
					elif character == '\x0d':
						return True
					else:
						new_line = self.history[self.historypos][:self.cursorpos] + character + self.history[self.historypos][self.cursorpos:]
						self.cursorpos += 1
					if new_line is not None:
						if self.historypos != len(self.history) - 1:
							# If not at the latest history position, go there.
							# This has the effect of making the history copy-on-write.
							# Which is desirable, because cows are desirable.
							self.historypos = len(self.history) - 1
						self.history[self.historypos] = new_line
					self.refresh()

			ifh, ofh, xfh = select.select([sys.stdin.fileno()], [], [], 0)
			keepGoing = len(ifh) > 0 and process_all_input
		return False
	def line(self, *values, sep=' ', end='', file=None, printfile=True, **kwargs):
		DotPrinterSlots.line(*values, sep=sep, end=end, file=file, printfile=printfile)
		self.refresh()
	def close(self, msg=None):
		DotPrinterSlots.lock()
		DotPrinterSlots.deregister(self, msg)
		DotPrinterSlots.release()
		Term.revert()
	def activation_cb(self):
		self.position_cursor()
		Term.enableCursor()
		self.dotfile.flush()
	def deactivation_cb(self):
		Term.disableCursor()
		self.dotfile.flush()
	def __del__(self):
		pass
		#if sys.meta_path is not None:
		#	self.close()

class Interpreter(EditingLine):
	def __init__(self, namespace=None, **kwargs):
		import code
		if 'prompt' not in kwargs:
			kwargs['prompt'] = ">>> "
		super().__init__(**kwargs)
		if namespace is None:
			self.ii = code.InteractiveInterpreter(globals())
		else:
			self.ii = code.InteractiveInterpreter(namespace)
		self.linebuf = []

	def runpy(self, source):
		import io
		sio = io.StringIO()
		origout, sys.stdout = sys.stdout, sio
		try:
			res = self.ii.runsource(source)
		finally:
			sys.stdout = origout
		return (res, sio)
	def poll(self):
		resp = super().poll()
		if resp:
			line = self.getBuf()
			self.reset(history=self.history)
			self.linebuf.append(line)
			source = "\n".join(self.linebuf)
			if len(self.linebuf) == 1:
				self.line(">>> {}".format(self.linebuf[-1]))
			else:
				self.line("... {}".format(self.linebuf[-1]))
			res, sio = self.runpy(source)
			if res is True:
				self.prompt = "... "
			else:
				self.prompt = ">>> "
				self.linebuf = []
				for line in sio.getvalue().splitlines():
					self.line(line)

class FancyFileReader:
	def __init__(self, fn, read_size=65536, omit_dirname=True):
		self.fn = fn
		self.stats = os.stat(fn)
		self.read_size = read_size
		sizestring = "{:n}".format(self.stats.st_size)
		if omit_dirname:
			self.label = os.path.basename(self.fn)
		else:
			self.label = self.fn
		self.fh = open(self.fn, "rb")
		self.bytesread = 0
		self.status = DotPrinter(self.stats.st_size, label=self.label, showcount=False, clear_on_close=True)
	def __iter__(self):
		return self
	def __next__(self):
		data = self.fh.read(self.read_size)
		if len(data) == 0:
			self.status.close()
			self.close()
			raise StopIteration
		self.bytesread += len(data)
		self.status.update(self.bytesread)
		return data
	def close(self):
		self.fh.close()

class DullFileReader:
	def __init__(self, fn, read_size=65536, omit_dirname=True):
		self.fn = fn
		self.fh = open(self.fn, "rb")
		self.read_size = read_size
	def __iter__(self):
		return self
	def __next__(self):
		data = self.fh.read(self.read_size)
		if len(data) == 0:
			self.close()
			raise StopIteration
		return data
	def close(self):
		self.fh.close()

def Prompt(text, validchars): # {{{
	"""
	Prompts the user to respond to a query in a single-character fashion.

	The prompt will repeat until a valid character is entered.

	:text: Derp
	"""
	gotchar = b''
	if isinstance(validchars, str):
		validchars = validchars.encode()
	while len(gotchar) < 1 or gotchar not in validchars:
		sys.stderr.write("{} ".format(text))
		sys.stderr.flush()
		gotchar = Term.getkey()
		sys.stderr.write("\n")
		sys.stderr.flush()
	return gotchar
# }}}
