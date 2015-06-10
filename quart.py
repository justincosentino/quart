"""

A quadtree computer art implementation based off of a similar project.

Justin Cosentino
6/9/2015

---

usage: quadtree.py [-h] [-g] image_path iterations scale

Generate quadtree computer art given a seed image.

positional arguments:
  image_path  the path to the image file
  iterations  the number of iterations the model performs
  scale       the factor by which to scale the output image

optional arguments:
  -h, --help  show this help message and exit
  -g, --gif   generate a gif of each iteration

"""

# --------------------------------------------------------------------------- #

from collections import defaultdict
from PIL import Image, ImageDraw
import argparse
import heapq
import os
import shutil
import subprocess
import sys
import tempfile

# --------------------------------------------------------------------------- #

class Quadrant:
	
	MIN_LEAF_SIZE = 4	# Minimum width and height of a quadrant
	
	def __init__(self, quad_model, coords, depth):
		"""A quadrant representing a portion of a PIL image.

	    quad_model 	-- the QuadModel managing the given quadrant
	    coords 		-- a tuple representing the coordinates of the quadrant,
	    			   in the form (left, top, right, bottom)
	    depth 		-- the recursive depth of the quadrant
		"""
		# Save parameter value
		self.quad_model = quad_model
		self.coords = coords
		self.depth = depth
		
		# Analyze given quadrant
		self.quad = self.quad_model.quad_im.im.crop(self.coords)
		self.color_hist = self.quad.histogram()
		self.area = self.compute_area()
		self.color, self.error 	= self.compute_color()
		self.leaf = self.is_leaf()
		self.children = []
		return

	def compute_area(self):
		"""Computes and returns the area (in pixels) of a quadrant."""
		l, t, r, b = self.coords
		return (b - t) * (r - l)
	
	def compute_color(self):
		"""Computers and returns the average RGB color of a quadrant as 
		well as the mean square error given this average.
		"""
		r, r_error = self.compute_avg_color_mse(self.color_hist[:256])
		g, g_error = self.compute_avg_color_mse(self.color_hist[256:512])
		b, b_error = self.compute_avg_color_mse(self.color_hist[512:])
		avg_error = (r_error + g_error + b_error) / 3.0
		return (r,g,b), avg_error

	def compute_avg_color_mse(self, hist):
		"""Determine the average value for a component of a RGB color and the 
		mean square error of the average value.

		hist -- a color histogram for the given RGB component
		"""
		ttl = sum(hist)
		
		# Prevent division by 0
		if ttl == 0: 
			ttl = 1

		avg = sum(i * num_pix for i, num_pix in enumerate(hist)) / ttl
		mse = sum((avg-i)**2 * num_pix for i, num_pix in enumerate(hist)) / ttl
		return avg, mse

	def is_leaf(self):
		"""Returns True if the quadrant cannot be split as it has reached 
		the minimum quadrant size. Return false otherwise.
		"""
		l, t, r, b = self.coords
		return r - l < self.MIN_LEAF_SIZE or b - t < self.MIN_LEAF_SIZE

	def split(self):
		"""Splits the quadrant into four children quadrants of equal size. 
		Returns a tuple of children quadrants in the form (top left, top right,
		bottom left, bottom right).
		"""
		# Initialize split conditions
		l, t, r, b = self.coords
		h_split = l + (r - l) / 2
		v_split = t + (b - t) / 2
		depth  = self.depth + 1

		# Construct new quadrants
		t_l = Quadrant(self.quad_model, (l, t, h_split, v_split), depth)
		t_r = Quadrant(self.quad_model, (h_split, t, r, v_split), depth)
		b_l = Quadrant(self.quad_model, (l, v_split, h_split, b), depth)
		b_r = Quadrant(self.quad_model, (h_split, v_split, r, b), depth)
		
		self.children = [t_l, t_r, b_l, b_r]
		return self.children

	def get_leaf_nodes(self):
		"""Recursively determine and return all children of the quadrant."""
		# Base case
		if not self.children:
			return [self]

		# Recursively fetch children
		leaf_nodes = []
		for child in self.children:
			leaf_nodes.extend(child.get_leaf_nodes())

		return leaf_nodes

# --------------------------------------------------------------------------- #

class QuadImage:
	def __init__(self, image_path):
		"""A quadrant image storing information related to the original seed 
		image. Stored using the Python Image Library (PIL).

	    image_path -- the relative or absolute path to the seed image.
		"""
		self.original = Image.open(image_path)
		self.im = self.original.convert('RGB')
		self.width, self.height = self.im.size
		return

# --------------------------------------------------------------------------- #

class QuadModel:

	FRAME_THRESHOLD = 50		# Error difference when saving frames
	QUAD_PADDING    = 1			# Padding around each quadrant when rendered
								# MUST BE AN INT
	PADDING_FILL    = (0,0,0) 	# (R,G,B)

	def __init__(self, image_path, scale=1.0):
		"""A model used to generate quadtree computer art.

	    image_path -- the relative or absolute path to the seed image.
	    scale 	   -- the factor by which to scale the output image
		"""
		# Initialize image properties
		self.quad_im = QuadImage(image_path)
		self.scale = scale
		self.fileprefix = image_path.rsplit('.',1)[0]
		if '/' in self.fileprefix: 
			self.fileprefix = self.fileprefix.rsplit('/',1)[1]

		# Construct root quadrant
		self.root = Quadrant(
			self, 
			(0, 0, self.quad_im.width, self.quad_im.height), 
			0
		)
		self.model_error = self.root.error * self.root.area

		# Initialize model heap
		self.heap = []
		self.push(self.root)
		return

	def compute_average_model_error(self):
		"""Computes and returns the average error per pixel in the image."""
		return self.model_error / (self.quad_im.width * self.quad_im.height)

	def push(self,quad):
		"""Pushes a quadrant onto the QuadModel heap. A weighted score is 
		computed using the quadrant's mean square error and area. Updates the 
		total model error.

		quad -- The quadrant being placed onto the heap.
		"""
		score = -quad.error * (quad.area ** .25)
		heapq.heappush(self.heap, (score, quad))
		self.model_error += quad.error * quad.area
		return

	def pop(self):
		"""Pops a quadrant off of the QuadModel heap and updates the total model
		error. Returns the quadrant.
		"""
		quad = heapq.heappop(self.heap)[-1]
		self.model_error -= quad.error * quad.area 
		return quad

	def split(self):
		"""Selects the quadrant with the greatest weighted mean square error 
		and splits it. Pushes the children of the quadrant onto the QuadModel
		heap.
		"""
		quad = self.pop()
		for child in quad.split():
			self.push(child)
		return

	def render(self, output_image_path):
		"""Renders the image using the quadrants currently stored within the 
		QuadModel heap. Saves the rendered image to the specified output path.

		output_image_path -- the relative path where the image should be saved.
		"""
		# Initialize rending constants
		dx, dy = self.QUAD_PADDING, self.QUAD_PADDING
		m = self.scale
		m_w, m_h = int(self.quad_im.width*m), int(self.quad_im.height*m)
		
		# Generate a new image on which quadrants will be drawn
		im = Image.new('RGB', (m_w+dx, m_h+dy))
		draw = ImageDraw.Draw(im)
		draw.rectangle((0, 0, m_w, m_h), self.PADDING_FILL)
		
		# Draw each quadrant and write the image
		for quad in self.root.get_leaf_nodes():
			l, t, r, b = quad.coords
			coords = (l*m + dx, t*m + dy, r*m - dx, b*m - dy)
			coords = [int(x) for x in coords]
			draw.rectangle(coords, quad.color)
		del draw
		im.save(output_image_path, 'PNG')
		return

	def recurse(self, iterations, tempdir=None):
		"""Recursively split the seed image for the specified number of 
		iterations. If a gif is being produced, write a frame to a temporary 
		directory if the error threshold is met.

		iterations -- the number of times to split the image.
		tempdir    -- the temporary directory in which to save gif frames. 
					  (default: none)
		"""
		prev_error = None
		for i in xrange(iterations):
			error = self.compute_average_model_error()
			if prev_error == None or prev_error - error > self.FRAME_THRESHOLD:
				if tempdir:
					frame_path = ''.join([
						tempdir, 
						'/', 
						'%06d_' % (i), 
						self.fileprefix, 
						'.png'
					])
					self.render(frame_path)
				prev_error = error
			self.split()
		self.render('%s_output.png' % (self.fileprefix))
		return

# --------------------------------------------------------------------------- #

def generate_gif(frame_dir, fileprefix, gif_type):
	"""Given a temporary directory, using imagemagick to convert a series of 
	frames into a gif. 

	frame_dir 	-- the temporary directory in which frames have been saved
	fileprefix	-- filename used for generating output, used for naming
	gif_type    -- the type of gif being produced, used for naming
	"""
	gif_cmd = ' '.join([
		"convert", 
	    "-loop 0", 
	    "-delay 20 %s/*.png" 		% (frame_dir), 
	    "-delay 200 %s_output.png" 	% (fileprefix),
	    "%s_%s.gif" 				% (fileprefix, gif_type)
	])
	subprocess.call(gif_cmd, shell=True)
	return

# --------------------------------------------------------------------------- #

def main():

	# Parse command line arguments
	parser = argparse.ArgumentParser(
		description='Generate quadtree computer art given a seed image.'
	)
	parser.add_argument(
		"image_path", 
		help="the path to the image file", 
		type=str
	)
	parser.add_argument(
		"iterations", 
		help="the number of iterations the model performs", 
		type=int
	)
	parser.add_argument(
		"scale", 
		help="the factor by which to scale the output image", 
		type=float
	)
	parser.add_argument(
		"-g", 
		"--gif", 
		help="generate a gif of each iteration", 
		action="store_true"
	)
	args = parser.parse_args()

	# Ensure valid pathname
	if not os.path.isfile(args.image_path):
		print "%s: error: invalid image_path" % (parser.prog)
		print 'exiting...'
		exit(1)

	# Generate a temporary directory to hold frames
	tempdir_gif = None
	if args.gif: 
		tempdir_gif = tempfile.mkdtemp()       

	try:
		# Run image model
		im_model = QuadModel(args.image_path, args.scale)
		im_model.recurse(args.iterations, tempdir_gif)

		# Generate gif if specified
		if args.gif:
			generate_gif(tempdir_gif, im_model.fileprefix, 'gif')

	except Exception as e:
		print '%s: error: %s' % (parser.prog, e) 
		print 'exiting...'
		exit(1)

	finally:
		# Remove the temporary directories and frames
		if tempdir_gif:	
			shutil.rmtree(tempdir_gif)

# --------------------------------------------------------------------------- #

if __name__ == '__main__':
	main()

# --------------------------------------------------------------------------- #
