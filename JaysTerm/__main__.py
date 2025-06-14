if __name__ == "__main__":
	import sys
	from JaysTerm import *
	import argparse
	description = "Outputs terminal dimensions on STDOUT"
	parser = argparse.ArgumentParser(description=description)
	parser.add_argument('-g', '--getkey', action='store_true', dest='getkey', default=False, help="getkey mode: waits for a single character of input from the terminal, and returns that character on STDOUT")
	args = parser.parse_args()

	if args.getkey:
		Term.init()
		key = Term.getkey(interruptable=False)
		print(key.decode())
		sys.exit(0)

	cols, rows = Term.getSize()
	print("{}x{}".format(cols, rows))
