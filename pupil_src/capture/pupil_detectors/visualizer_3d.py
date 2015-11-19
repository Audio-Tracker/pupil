
import logging
from glfw import *
from OpenGL.GL import *
from OpenGL.GLU import gluOrtho2D

# create logger for the context of this function
logger = logging.getLogger(__name__)
from pyglui import ui

from pyglui.cygl.utils import init
from pyglui.cygl.utils import RGBA
from pyglui.cygl.utils import *
from pyglui.cygl import utils as glutils
from trackball import Trackball
from pyglui.pyfontstash import fontstash as fs
from pyglui.ui import get_opensans_font_path
import numpy as np
import math
import cv2
import random

import build_test

def convert_fov(fov,width):
	fov = fov* math.pi/180
	focal_length = (width/2)/np.tan(fov/2)
	return focal_length

def get_perpendicular_vector(v):
    """ Finds an arbitrary perpendicular vector to *v*."""
    # http://codereview.stackexchange.com/questions/43928/algorithm-to-get-an-arbitrary-perpendicular-vector
    # for two vectors (x, y, z) and (a, b, c) to be perpendicular,
    # the following equation has to be fulfilled
    #     0 = ax + by + cz

    # x = y = z = 0 is not an acceptable solution
    if v[0] == v[1] == v[2] == 0:
        logger.error('zero-vector')

    # If one dimension is zero, this can be solved by setting that to
    # non-zero and the others to zero. Example: (4, 2, 0) lies in the
    # x-y-Plane, so (0, 0, 1) is orthogonal to the plane.
    if v[0] == 0:
        return np.array((1, 0, 0))
    if v[1] == 0:
        return np.array((0, 1, 0))
    if v[2] == 0:
        return np.array((0, 0, 1))

    # arbitrarily set a = b = 1
    # then the equation simplifies to
    #     c = -(x + y)/z
    return np.array([1, 1, -1.0 * (v[0] + v[1]) / v[2]])

circle_xy = [] #this is a global variable
circle_res = 30.0
for i in range(0,int(circle_res+1)):
	temp =  (i)/circle_res *  math.pi * 2.0
	circle_xy.append([np.cos(temp),np.sin(temp)])

class Visualizer(object):
	def __init__(self,focal_length, name = "Debug Visualizer", run_independently = False):
       # super(Visualizer, self).__init__()
		self.focal_length = focal_length
		self.image_width = 640 # right values are assigned in update
		self.image_height = 480
		# transformation matrices
		self.anthromorphic_matrix = self.get_anthropomorphic_matrix()
		self.adjusted_pixel_space_matrix = self.get_adjusted_pixel_space_matrix(1)

		self.name = name
		self.window_size = (640,480)
		self._window = None
		self.input = None
		self.run_independently = run_independently

		camera_fov = math.degrees(2.0 * math.atan( self.window_size[0] / (2.0 * self.focal_length)))
		self.trackball = Trackball(camera_fov)

	############## MATRIX FUNCTIONS ##############################

	def get_anthropomorphic_matrix(self):
		temp =  np.identity(4)
		return temp

	def get_adjusted_pixel_space_matrix(self):
		temp =  np.identity(4)
		return temp

	def get_adjusted_pixel_space_matrix(self,scale):
		# returns a homoegenous matrix
		temp = self.get_anthropomorphic_matrix()
		temp[3,3] *= scale
		return temp

	def get_image_space_matrix(self,scale=1.):
		temp = self.get_adjusted_pixel_space_matrix(scale)
		temp[1,1] *=-1 #image origin is top left
		temp[0,3] = -self.image_width/2.0
		temp[1,3] = self.image_height/2.0
		temp[2,3] = self.focal_length
		return temp.T

	def get_pupil_transformation_matrix(self,circle_normal,circle_center, circle_scale = 1.0):
		"""
			OpenGL matrix convention for typical GL software
			with positive Y=up and positive Z=rearward direction
			RT = right
			UP = up
			BK = back
			POS = position/translation
			US = uniform scale

			float transform[16];

			[0] [4] [8 ] [12]
			[1] [5] [9 ] [13]
			[2] [6] [10] [14]
			[3] [7] [11] [15]

			[RT.x] [UP.x] [BK.x] [POS.x]
			[RT.y] [UP.y] [BK.y] [POS.y]
			[RT.z] [UP.z] [BK.z] [POS.Z]
			[    ] [    ] [    ] [US   ]
		"""
		temp = self.get_anthropomorphic_matrix()
		right = temp[:3,0]
		up = temp[:3,1]
		back = temp[:3,2]
		translation = temp[:3,3]
		back[:] = np.array(circle_normal)
		# if np.linalg.norm(back) != 0:
		back[:] /= np.linalg.norm(back)
		right[:] = get_perpendicular_vector(back)/np.linalg.norm(get_perpendicular_vector(back))
		up[:] = np.cross(right,back)/np.linalg.norm(np.cross(right,back))
		right[:] *= circle_scale
		back[:] *=circle_scale
		up[:] *=circle_scale
		translation[:] = np.array(circle_center)
		return   temp.T

	############## DRAWING FUNCTIONS ##############################

	def draw_frustum(self, scale=1):

		W = self.image_width/2.0
		H = self.image_height/2.0
		Z = self.focal_length
		# scale the pyramid
		W *= scale
		H *= scale
		Z *= scale
		# draw it
		glLineWidth(1)
		glColor4f( 1, 0.5, 0, 0.5 )
		glBegin( GL_LINE_LOOP )
		glVertex3f( 0, 0, 0 )
		glVertex3f( -W, H, Z )
		glVertex3f( W, H, Z )
		glVertex3f( 0, 0, 0 )
		glVertex3f( W, H, Z )
		glVertex3f( W, -H, Z )
		glVertex3f( 0, 0, 0 )
		glVertex3f( W, -H, Z )
		glVertex3f( -W, -H, Z )
		glVertex3f( 0, 0, 0 )
		glVertex3f( -W, -H, Z )
		glVertex3f( -W, H, Z )
		glEnd( )

	def draw_coordinate_system(self,l=1):
		# Draw x-axis line. RED
		glLineWidth(2)
		glColor3f( 1, 0, 0 )
		glBegin( GL_LINES )
		glVertex3f( 0, 0, 0 )
		glVertex3f( l, 0, 0 )
		glEnd( )

		# Draw y-axis line. GREEN.
		glColor3f( 0, 1, 0 )
		glBegin( GL_LINES )
		glVertex3f( 0, 0, 0 )
		glVertex3f( 0, l, 0 )
		glEnd( )

		# Draw z-axis line. BLUE
		glColor3f( 0, 0,1 )
		glBegin( GL_LINES )
		glVertex3f( 0, 0, 0 )
		glVertex3f( 0, 0, l )
		glEnd( )

	def draw_sphere(self,sphere_position, sphere_radius,contours = 45):
		# this function draws the location of the eye sphere
		glPushMatrix()

		glTranslatef(sphere_position[0],sphere_position[1],sphere_position[2]) #sphere[0] contains center coordinates (x,y,z)
		glTranslatef(0,0,sphere_radius) #sphere[1] contains radius
		for i in xrange(1,contours+1):

			glTranslatef(0,0, -sphere_radius/contours*2)
			position = sphere_radius - i*sphere_radius*2/contours
			draw_radius = np.sqrt(sphere_radius**2 - position**2)
			glPushMatrix()
			glScalef(draw_radius,draw_radius,1)
			draw_polyline((circle_xy),2,color=RGBA(.2,.5,0.5,.5))
			glPopMatrix()

		glPopMatrix()

	def draw_all_ellipses(self,eye_model_fitter,number = 0):
		# draws all ellipses in model. numder determines last x amt of ellipses to show
		glPushMatrix()
		if number == 0 or number > eye_model_fitter.num_observations: #print everything. or statement in case try to access too many
			for pupil in eye_model_fitter.get_all_pupil_observations():
				#ellipse is pupil[0]. ellipse is ([x,y], major, minor, angle)
				glColor3f(0.0, 1.0, 0.0)  #set color to green
				pts = cv2.ellipse2Poly( (int(pupil.ellipse_center[0]),int(pupil.ellipse_center[1])),
	                              (int(pupil.ellipse_major_radius), int(pupil.ellipse_minor_radius) ),
	                              int(pupil.ellipse_angle*180/math.pi),
	                              0,360,15)

				draw_polyline(pts,4,color = RGBA(0,1,1,.5))
		else:
			for pupil in eye_model_fitter.get_last_pupil_observations(number):
				#ellipse is pupil[0]. ellipse is ([x,y], major, minor, angle)
				glColor3f(0.0, 1.0, 0.0)  #set color to green
				pts = cv2.ellipse2Poly( (int(pupil.ellipse_center[0]),int(pupil.ellipse_center[1])),
	                              (int(pupil.ellipse_major_radius), int(pupil.ellipse_minor_radius) ),
	                              int(pupil.ellipse_angle*180/math.pi),
	                              0,360,15)
				draw_polyline(pts,4,color = RGBA(0,1,1,.5))
		glPopMatrix()

	def draw_all_circles(self,eye_model_fitter,number = 0):
		if number == 0 or number > eye_model_fitter.num_observations: #print everything. or statement in case try to access too many
			for pupil in eye_model_fitter.get_all_pupil_observations():
				#circle is pupil[2]. circle is (center[x,y,z], normal[x,y,z], radius)
				glPushMatrix()
				glLoadMatrixf(self.get_pupil_transformation_matrix(pupil[2][1],pupil[2][0])) #circle normal, center
				draw_points(((0,0),),color=RGBA(1.1,0.2,.8))
				glScalef(pupil[2][2],pupil[2][2],1) #scale by pupil radius
				draw_polyline((circle_xy),color=RGBA(0.,0.,0.,.5), line_type = GL_POLYGON)
				glColor4f(0.0, 0.0, 0.0,0.5)  #set color to green
				glBegin(GL_POLYGON) #draw circle
				glEnd()
				glPopMatrix()
		else:
			for pupil in eye_model_fitter.get_last_pupil_observations(number):
				#circle is pupil[2]. circle is (center[x,y,z], normal[x,y,z], radius)
				glPushMatrix()
				glLoadMatrixf(self.get_pupil_transformation_matrix(pupil[2][1],pupil[2][0])) #circle normal, center
				draw_points(((0,0),),color=RGBA(1.1,0.2,.8))
				glScalef(pupil[2][2],pupil[2][2],1) #scale by pupil radius
				draw_polyline((circle_xy),color=RGBA(0.,0.,0.,.5), line_type = GL_POLYGON)
				glColor4f(0.0, 0.0, 0.0,0.5)  #set color to green
				glBegin(GL_POLYGON) #draw circle
				glEnd()
				glPopMatrix()


	def draw_circle(self, circle_center, circle_normal, circle_radius, color=RGBA(1.1,0.2,.8), num_segments = 20):
		vertices = []
		vertices.append( (0,0,0) )  # circle center

		#create circle vertices in the xy plane
		for i in np.linspace(0.0, 2.0*math.pi , num_segments ):
			x = math.sin(i)
			y = math.cos(i)
			z = 0
			vertices.append((x,y,z))

		glMatrixMode(GL_MODELVIEW )
		glPushMatrix()
		glLoadMatrixf(self.get_pupil_transformation_matrix(circle_normal,circle_center, circle_radius))
		draw_polyline((vertices),color=color, line_type = GL_TRIANGLE_FAN) # circle
		draw_polyline( [ (0,0,0), (0,0, 4) ] ,color=RGBA(0,0,0), line_type = GL_LINES) #normal
		glPopMatrix()



	def draw_contours_on_screen(self,contours, color = RGBA(0.,0.,0.,0.5)):
		#this function displays the contours on the 2D video stream within the visualizer module
		glPushMatrix()
		glLoadMatrixf(self.get_image_space_matrix(30))
		for contour in contours:
			draw_polyline(contour,color)
		glPopMatrix()

	def draw_contours(self, contours, thickness = 1, color = RGBA(0.,0.,0.,0.5) ):
		glPushMatrix()
		glLoadMatrixf(self.get_anthropomorphic_matrix())
		for contour in contours:
			draw_polyline(contour, thickness, color = color )
		glPopMatrix()

	def draw_contour(self, contour, thickness = 1, color = RGBA(0.,0.,0.,0.5) ):
		glPushMatrix()
		glLoadMatrixf(self.get_anthropomorphic_matrix())
		draw_polyline(contour,thickness, color)
		glPopMatrix()

	def draw_unwrapped_contours_on_screen( self, contours, screen_pos = (20,20), size =(400,400)):

		glViewport(screen_pos[0],screen_pos[1], size[0], size[1])
		glMatrixMode(GL_PROJECTION)
		glPushMatrix()
		glLoadIdentity()
		glOrtho(0,1, 1,0, -1 , 1 )
		glMatrixMode(GL_MODELVIEW)
		glPushMatrix()
		glLoadIdentity()

		bottom_left = (0,0);
		top_left = (0,1)
		top_right = (1,1)
		bottom_right = (1,0)

		#draw lines around the current viewport, to show border
		quad = [bottom_left, top_left, top_right, bottom_right]
		draw_polyline( quad,color=RGBA(0.,0.,0.,1.0), line_type= GL_LINE_LOOP)

		for contour in contours:
			draw_polyline(contour,color=RGBA(0.,0.,0.,1.0))

		glPopMatrix()
		glMatrixMode(GL_PROJECTION)
		glPopMatrix()
		glMatrixMode(GL_MODELVIEW )

		glViewport(0,0, self.window_size[0], self.window_size[1])


	def draw_eye_model_fitter_text(self, eye, gaze_vector, pupil_radius  ):

		status = ' Eyeball center : X%.2fmm Y%.2fmm Z%.2fmm\n Gaze vector (currently WRONG):  X%.2f Y%.2f Z%.2f\n Pupil Diameter: %.2fmm\n  ' \
		%(eye[0][0], eye[0][1],eye[0][2],
		gaze_vector[0], gaze_vector[1],gaze_vector[2], pupil_radius*2)
		self.glfont.draw_multi_line_text(5,20,status)
		self.glfont.draw_multi_line_text(440,20,'View: %.2f %.2f %.2f'%(self.trackball.distance[0],self.trackball.distance[1],self.trackball.distance[2]))

	########## Setup functions I don't really understand ############

	def basic_gl_setup(self):
		glEnable(GL_POINT_SPRITE )
		glEnable(GL_VERTEX_PROGRAM_POINT_SIZE) # overwrite pointsize
		glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
		glEnable(GL_BLEND)
		glClearColor(.8,.8,.8,1.)
		glEnable(GL_LINE_SMOOTH)
		# glEnable(GL_POINT_SMOOTH)
		glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
		glEnable(GL_LINE_SMOOTH)
		glEnable(GL_POLYGON_SMOOTH)
		glHint(GL_POLYGON_SMOOTH_HINT, GL_NICEST)

	def adjust_gl_view(self,w,h):
		"""
		adjust view onto our scene.
		"""
		glViewport(0, 0, w, h)
		glMatrixMode(GL_PROJECTION)
		glLoadIdentity()
		glOrtho(0, w, h, 0, -1, 1)
		glMatrixMode(GL_MODELVIEW)
		glLoadIdentity()

	def clear_gl_screen(self):
		glClearColor(.9,.9,0.9,1.)
		glClear(GL_COLOR_BUFFER_BIT)

	########### Open, update, close #####################

	def open_window(self):
		if not self._window:
			self.input = {'button':None, 'mouse':(0,0)}

			# get glfw started
			if self.run_independently:
				glfwInit()
			window = glfwGetCurrentContext()
			self._window = glfwCreateWindow(self.window_size[0], self.window_size[1], self.name, None, window)
			glfwMakeContextCurrent(self._window)

			if not self._window:
				exit()

			glfwSetWindowPos(self._window,0,0)
			# Register callbacks window
			glfwSetFramebufferSizeCallback(self._window,self.on_resize)
			glfwSetWindowIconifyCallback(self._window,self.on_iconify)
			glfwSetKeyCallback(self._window,self.on_key)
			glfwSetCharCallback(self._window,self.on_char)
			glfwSetMouseButtonCallback(self._window,self.on_button)
			glfwSetCursorPosCallback(self._window,self.on_pos)
			glfwSetScrollCallback(self._window,self.on_scroll)
			glfwSetWindowCloseCallback(self._window,self.on_close)

			# get glfw started
			if self.run_independently:
				init()
			self.basic_gl_setup()

			self.glfont = fs.Context()
			self.glfont.add_font('opensans',get_opensans_font_path())
			self.glfont.set_size(22)
			self.glfont.set_color_float((0.2,0.5,0.9,1.0))
			self.on_resize(self._window,*glfwGetFramebufferSize(self._window))
			glfwMakeContextCurrent(window)

			# self.gui = ui.UI()

	def update_window(self, g_pool, image_width, image_height,  eye, detector_3D  ):

		if self._window != None:
			glfwMakeContextCurrent(self._window)

		if image_height and image_width:
			self.image_width = image_width # reassign in case the image size got changed during running
			self.image_height = image_height

		latest_pupil = detector_3D.get_latest_pupil()
		last_unprojected_contours =  detector_3D.get_last_pupil_contours()
		final_circle_contours = detector_3D.get_last_final_circle_contour()
		#last_pupil_edges = detector_3D.get_last_pupil_edges()
		#final_candidate_contours = detector_3D.get_last_final_candidate_contour()
		bin_positions = detector_3D.get_bin_positions()

		self.clear_gl_screen()
		self.trackball.push()

		eye_position = eye[0]
		eye_radius = eye[1]


		self.draw_coordinate_system(4)

		self.draw_sphere(eye_position,eye_radius)

		self.draw_circle( latest_pupil[0], latest_pupil[1], latest_pupil[2], RGBA(0.0,1.0,1.0,0.4))


		#draw unprojecte contours
		if last_unprojected_contours:
			self.draw_contours(last_unprojected_contours, 1, RGBA(1.,0.,0.,1.))
		#self.draw_contours_on_screen(projected_contours)

		#draw contour which are a candidate
		colors = [RGBA(0.5,0.5,0.,1.),RGBA(0.5,0.5,1.,1.),RGBA(1.0,0.0,1.,1.),RGBA(0.0,1.0,1.,1.),RGBA(1.0,0.5,0.,1.)]
		# if final_candidate_contours:
		# 	glPushMatrix()
		# 	glLoadMatrixf(self.get_anthropomorphic_matrix())
		# 	i = 0
		# 	for contours in final_candidate_contours:
		# 		self.draw_contours(contours, 1, colors[i%len(colors)] )
		# 		i += 1
		# 	glPopMatrix()



		#draw contour used for the final circle fit
		if final_circle_contours:
			self.draw_contours(final_circle_contours, 3 , RGBA(0.,1.,0.,1.) )

		#if last_pupil_edges:
		#	draw_polyline(last_pupil_edges, 3 , RGBA(0.,0.,0.,1.), line_type = GL_POINTS )


		if bin_positions:
			draw_points(bin_positions, 5 , RGBA(0.,1.,0.,1.) )

		# 1b. draw frustum in pixel scale, but retaining origin
		glLoadMatrixf(self.get_adjusted_pixel_space_matrix(17))
		self.draw_frustum()

		# 2. in pixel space draw video frame
		#glLoadMatrixf(self.get_image_space_matrix(17))
		#g_pool.image_tex.draw( quad=((0,480),(640,480),(640,0),(0,0)) ,alpha=0.5)


		self.trackball.pop()
		#if last_unwrapped_contours:
		#	self.draw_unwrapped_contours_on_screen(last_unwrapped_contours)
		gaze_vector = detector_3D.get_gaze_vector()
		pupil_radius = latest_pupil[2]
		self.draw_eye_model_fitter_text(eye, gaze_vector,pupil_radius)

		glfwSwapBuffers(self._window)
		glfwPollEvents()
		return True

	def close_window(self):
		if self._window:
			glfwDestroyWindow(self._window)
			self._window = None

	############ window callbacks #################
	def on_resize(self,window,w, h):
		h = max(h,1)
		w = max(w,1)
		self.trackball.set_window_size(w,h)

		self.window_size = (w,h)
		active_window = glfwGetCurrentContext()
		glfwMakeContextCurrent(window)
		self.adjust_gl_view(w,h)
		glfwMakeContextCurrent(active_window)

	def on_button(self,window,button, action, mods):
		# self.gui.update_button(button,action,mods)
		if action == GLFW_PRESS:
			self.input['button'] = button
			self.input['mouse'] = glfwGetCursorPos(window)
		if action == GLFW_RELEASE:
			self.input['button'] = None

	def on_pos(self,window,x, y):
		hdpi_factor = float(glfwGetFramebufferSize(window)[0]/glfwGetWindowSize(window)[0])
		x,y = x*hdpi_factor,y*hdpi_factor
		# self.gui.update_mouse(x,y)
		if self.input['button']==GLFW_MOUSE_BUTTON_RIGHT:
			old_x,old_y = self.input['mouse']
			self.trackball.drag_to(x-old_x,y-old_y)
			self.input['mouse'] = x,y
		if self.input['button']==GLFW_MOUSE_BUTTON_LEFT:
			old_x,old_y = self.input['mouse']
			self.trackball.pan_to(x-old_x,y-old_y)
			self.input['mouse'] = x,y

	def on_scroll(self,window,x,y):
		self.trackball.zoom_to(y)

	def on_close(self,window=None):
		pass
		#self.close_window()

	def on_iconify(self,window,x,y): pass
	def on_key(self,window, key, scancode, action, mods): pass
	def on_char(self,window,char): pass


# if __name__ == '__main__':
# 	print "done"

# 	huding = build_test.eye_model_fitter_3d.PyEyeModelFitter(focal_length=879.193, x_disp = 320, y_disp = 240)
# 	# print model
# 	huding.add_observation([422.255,255.123],40.428,30.663,1.116)
# 	huding.add_observation([442.257,365.003],44.205,32.146,1.881)
# 	huding.add_observation([307.473,178.163],41.29,22.765,0.2601)
# 	huding.add_observation([411.339,290.978],51.663,41.082,1.377)
# 	huding.add_observation([198.128,223.905],46.852,34.949,2.659)
# 	huding.add_observation([299.641,177.639],40.133,24.089,0.171)
# 	huding.add_observation([211.669,212.248],46.885,33.538,2.738)
# 	huding.add_observation([196.43,236.69],47.094,38.258,2.632)
# 	huding.add_observation([317.584,189.71],42.599,27.721,0.3)
# 	huding.add_observation([482.762,315.186],38.397,23.238,1.519)
# 	huding.update_model()

# 	# print huding.print_eye()
# 	# for pupil in huding.get_all_pupil_observations():
# 	# 		#circle is pupil[2]. circle is (center[x,y,z], normal[x,y,z], radius)
# 	# 		print pupil[2]

# 	# contours = [[[[38, 78]], [[39, 78]]],
# 	# 	[[[ 65, 40]], [[ 66, 39]], [[ 67, 40]], [[ 68, 40]], [[ 69, 41]], [[ 70, 41]], [[ 71, 40]], [[ 72, 41]], [[ 73, 41]], [[ 74, 41]], [[ 75, 42]], [[ 76, 42]], [[ 77, 42]], [[ 78, 42]], [[ 79, 43]], [[ 80, 44]], [[ 81, 45]], [[ 82, 45]], [[ 83, 45]], [[ 84, 46]], [[ 85, 46]], [[ 86, 47]], [[ 87, 47]], [[ 88, 48]], [[ 89, 49]], [[ 90, 50]], [[ 90, 51]],[[ 91, 52]],[[ 92, 53]],[[ 93, 53]],[[ 94, 54]],[[ 95, 55]],[[ 96, 56]],[[ 96, 57]],[[ 97, 58]],[[ 98, 59]],[[ 99, 60]],[[ 99, 61]],[[100, 62]],[[100, 63]],[[100, 64]], [[101, 65]],[[101, 66]],[[102, 67]],[[102, 68]],[[103, 69]], [[103, 70]],[[103, 71]], [[104, 72]],[[104, 73]],[[104, 74]],[[104, 75]],[[104, 76]],[[104, 77]],[[104, 78]],[[104, 79]], [[104, 80]],[[104, 81]],[[104, 82]],[[104, 83]],[[104, 84]],[[104, 85]], [[103, 86]],[[103, 87]],[[103, 88]], [[103, 89]],[[103, 90]],[[103, 91]],[[102, 92]], [[101, 93]],[[101, 94]],[[100, 95]], [[100, 96]],[[ 99, 97]],[[ 98, 98]],[[ 97, 99]], [[ 96, 100]],[[ 95, 101]],[[ 94, 101]],[[ 93, 102]],[[ 92, 103]],[[ 91, 103]], [[ 90, 104]],[[ 89, 104]],[[ 88, 104]],[[ 87, 104]],[[ 86, 104]],[[ 85, 105]],[[ 84, 105]],[[ 83, 105]],[[ 82, 105]],[[ 81, 105]],[[ 80, 106]],[[ 79, 106]],[[ 78, 106]],[[ 77, 106]],[[ 76, 106]],[[ 75, 105]],[[ 74, 105]],[[ 73, 105]],[[ 72, 105]],[[ 71, 104]],[[ 70, 104]],[[ 69, 104]],[[ 68, 104]],[[ 67, 103]],[[ 66, 103]],[[ 65, 102]],[[ 64, 101]],[[ 63, 100]],[[ 62, 100]], [[ 61, 99]],[[ 60, 99]],[[ 59, 98]],[[ 58, 97]],[[ 57, 97]], [[ 56, 96]],[[ 55, 95]],[[ 54, 94]],[[ 53, 93]],[[ 52, 92]],[[ 51, 91]],[[ 51, 90]], [[ 50, 89]], [[ 49, 88]],[[ 48, 87]],[[ 47, 86]],[[ 47, 85]],[[ 47, 84]], [[ 46, 83]], [[ 45, 82]],[[ 45, 81]],[[ 45, 80]],[[ 45, 79]],[[ 44, 78]],[[ 44, 77]],[[ 43, 76]],[[ 43, 75]],[[ 43, 74]],[[ 42, 73]],[[ 42, 72]],[[ 42, 71]], [[ 42, 70]],[[ 41, 69]],[[ 41, 68]],[[ 41, 67]],[[ 41, 66]],[[ 41, 65]], [[ 41, 64]],[[ 41, 63]],[[ 41, 62]], [[ 41, 61]],[[ 41, 60]], [[ 41, 59]], [[ 41, 58]],[[ 42, 57]],[[ 42, 56]],[[ 43, 55]],[[ 43, 54]],[[ 44, 53]],[[ 44, 52]],[[ 45, 51]],[[ 45, 50]],[[ 46, 49]],[[ 47, 48]],[[ 48, 47]],[[ 49, 47]],[[ 50, 46]],[[ 51, 45]],[[ 52, 45]],[[ 53, 44]],[[ 54, 43]],[[ 55, 42]],[[ 56, 42]],[[ 57, 41]],[[ 58, 41]],[[ 59, 41]],[[ 60, 41]],[[ 61, 41]],[[ 62, 40]],[[ 63, 40]],[[ 64, 40]]]
# 	# 	[[[ 66, 39]],[[ 65, 40]],[[ 64, 40]],[[ 63, 40]],[[ 62, 40]],[[ 61, 41]],[[ 60, 41]],[[ 59, 41]],[[ 58, 41]],[[ 57, 41]],[[ 56, 42]],[[ 55, 42]],[[ 54, 42]],[[ 53, 43]],[[ 52, 44]],[[ 51, 45]],[[ 50, 45]],[[ 49, 46]],[[ 48, 47]],[[ 47, 47]],[[ 46, 48]],[[ 45, 49]],[[ 45, 50]],[[ 44, 51]],[[ 44, 52]],[[ 43, 53]],[[ 43, 54]],[[ 42, 55]],[[ 42, 56]],[[ 42, 57]],[[ 41, 58]],[[ 41, 59]],[[ 41, 60]],[[ 41, 61]],[[ 41, 62]],[[ 41, 63]],[[ 41, 64]],[[ 41, 65]],[[ 41, 66]],[[ 41, 67]],[[ 41, 68]],[[ 41, 69]],[[ 42, 70]],[[ 42, 71]], [[ 42, 72]],[[ 42, 73]],[[ 43, 74]],[[ 43, 75]],[[ 43, 76]],[[ 44, 77]],[[ 44, 78]],[[ 44, 79]],[[ 45, 80]],[[ 45, 81]],[[ 45, 82]],[[ 46, 83]],[[ 46, 84]],[[ 47, 85]],[[ 47, 86]],[[ 48, 87]],[[ 48, 88]],[[ 49, 89]],[[ 50, 90]],[[ 51, 91]],[[ 51, 92]],[[ 52, 93]],[[ 53, 94]],[[ 54, 95]],[[ 55, 96]],[[ 56, 97]],[[ 57, 97]],[[ 58, 98]],[[ 59, 99]],[[ 60, 99]],[[ 61, 100]],[[ 62, 100]],[[ 63, 101]],[[ 64, 102]],[[ 65, 103]],[[ 66, 103]],[[ 67, 103]],[[ 68, 104]],[[ 69, 104]],[[ 70, 104]],[[ 71, 104]],[[ 72, 105]],[[ 73, 105]],[[ 74, 105]],[[ 75, 105]],[[ 76, 106]],[[ 77, 106]],[[ 78, 106]],[[ 79, 106]],[[ 80, 106]],[[ 81, 105]], [[ 82, 105]],[[ 83, 105]],[[ 84, 105]],[[ 85, 105]],[[ 86, 104]],[[ 87, 104]],[[ 88, 104]],[[ 89, 104]],[[ 90, 104]],[[ 91, 103]],[[ 92, 103]],[[ 93, 103]],[[ 94, 102]],[[ 95, 101]],[[ 96, 101]],[[ 97, 100]],[[ 98, 99]],[[ 99, 98]],[[100, 97]],[[100, 96]],[[101, 95]],[[101, 94]],[[102, 93]],[[103, 92]],[[103, 91]],[[103, 90]],[[103, 89]],[[103, 88]],[[103, 87]],[[103, 86]],[[104, 85]],[[104, 84]],[[104, 83]],[[104, 82]],[[104, 81]],[[104, 80]],[[104, 79]],[[104, 78]],[[104, 77]],[[104, 76]],[[104, 75]], [[104, 74]],[[104, 73]],[[104, 72]],[[103, 71]],[[103, 70]],[[103, 69]],[[102, 68]],[[102, 67]],[[102, 66]],[[101, 65]],[[101, 64]],[[100, 63]],[[100, 62]],[[ 99, 61]],[[ 99, 60]],[[ 99, 59]],[[ 98, 58]],[[ 97, 57]],[[ 96, 56]],[[ 96, 55]],[[ 95, 54]],[[ 94, 53]],[[ 93, 53]],[[ 92, 52]],[[ 91, 51]],[[ 90, 50]],[[ 90, 49]],[[ 89, 48]],[[ 88, 47]],[[ 87, 47]],[[ 86, 46]],[[ 85, 46]],[[ 84, 45]],[[ 83, 45]],[[ 82, 44]],[[ 81, 44]],[[ 80, 43]],[[ 79, 42]],[[ 78, 42]],[[ 77, 42]], [[ 76, 42]],[[ 75, 42]],[[ 74, 41]],[[ 73, 41]],[[ 72, 41]],[[ 71, 40]],[[ 70, 41]],[[ 69, 41]],[[ 68, 40]],[[ 67, 40]]]]
# 	contours = [[[[20,20]],[[21,20]],[[22,23]]]]

# 	intrinsics = np.matrix('879.193 0 320; 0 -879.193 240; 0 0 1')
# 	visualhuding = Visualizer("huding", run_independently = True, intrinsics = intrinsics)

# 	# print visualhuding.sphere_intersect([320,240],((0,0,49),12))

# 	visualhuding.open_window()
# 	a = 0
# 	while visualhuding.update_window(eye_model_fitter = huding, contours = contours):
# 	# while visualhuding.update_window(eye_model_fitter = huding):
# 		a += 1
# 	# visualhuding.update_window(eye_model_fitter = huding)
# 	visualhuding.close_window()
# 	print a