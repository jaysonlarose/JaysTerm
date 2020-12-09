#!/usr/bin/env python

from distutils.core import setup

version = __import__("JaysTerm").__version__
setup(
	name = "JaysTerm",
	version = version,
	author = "Jayson Larose",
	author_email = "jayson@interlaced.org",
	url = "https://github.com/jaysonlarose/JaysTerm",
	description = "Jays' Terminal Handling Library",
	download_url = f"https://github.com/jaysonlarose/JaysTerm/releases/download/{version}/JaysTerm-{version}.tar.gz",
	packages=['JaysTerm'],
	requires=['jlib'],
)
