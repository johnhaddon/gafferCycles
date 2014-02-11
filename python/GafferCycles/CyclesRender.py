##########################################################################
#  
#  Copyright (c) 2014, John Haddon. All rights reserved.
#  
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#  
#      * Redistributions of source code must retain the above
#        copyright notice, this list of conditions and the following
#        disclaimer.
#  
#      * Redistributions in binary form must reproduce the above
#        copyright notice, this list of conditions and the following
#        disclaimer in the documentation and/or other materials provided with
#        the distribution.
#  
#      * Neither the name of John Haddon nor the names of
#        any other contributors to this software may be used to endorse or
#        promote products derived from this software without specific prior
#        written permission.
#  
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
#  IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
#  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
#  CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
#  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
#  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
#  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#  SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#  
##########################################################################

import os

import IECore

import Gaffer
import GafferScene

class CyclesRender( GafferScene.ExecutableRender ) :

	def __init__( self, name = "CyclesRender" ) :
	
		GafferScene.ExecutableRender.__init__( self, name )
		
		self.addChild(
			Gaffer.StringPlug(
				"mode",
				Gaffer.Plug.Direction.In,
				"render",
			)
		)

		self.addChild(
			Gaffer.StringPlug(
				"xmlFileName",
			)
		)

	def execute( self, contexts ) :
	
		for context in contexts :
			self.__execute( context )
			
	def __execute( self, context ) :
	
		with context :
		
			fileName = self["xmlFileName"].getValue()
			fileName = context.substitute( fileName )
			
			if not fileName :
				return
				
			directory = os.path.dirname( fileName )
			if directory :
				try :
					os.makedirs( directory )
				except OSError :
					# makedirs very unhelpfully raises an exception if
					# the directory already exists, but it might also
					# raise if it fails. we reraise only in the latter case.
					if not os.path.isdir( directory ) :
						raise
						
			with open( fileName, "w" ) as f :
				self.__writeScene( f )
				
			if self["mode"].getValue() == "render" :
				os.system( "cycles '%s'&" % fileName )
			
	def __writeScene( self, f ) :
	
		globals = self["in"]["globals"].getValue()
		self.__writeCamera( f, globals )
	
		f.write(
			'<background>\n'
			'	<background name="bg" strength="2.0" color="0.2, 0.2, 0.2" />\n'
			'	<connect from="bg background" to="output surface" />\n'
			'</background>\n\n'
		)
		
		state = {
			"transform" : IECore.M44f(),
		}
		
		self.__walkScene( f, state, IECore.InternedStringVectorData() )
	
	def __writeCamera( self, f, globals ) :
	
		camera = None
		cameraTransform = IECore.M44f()
		
		cameraPath = globals.get( "render:camera", None )
		if cameraPath is not None :
			camera = self["in"].object( cameraPath.value )
			if isinstance( camera, IECore.Camera ) :
				cameraTransform = self["in"].fullTransform( cameraPath.value )
			else :		
				camera = None
			
		if camera is None :
			camera = IECore.Camera()
			
		resolution = globals.get( "render:resolution", None )
		if resolution is not None :
			camera.parameters()["resolution"] = resolution
			
		camera.addStandardParameters()
		
		cameraTransform.scale( IECore.V3f( 1, 1, -1 ) )
		
		f.write( '<transform matrix="' + str( cameraTransform ) + '">\n' )
		f.write( "<camera" )
		f.write( ' width="%d" height="%d"' % ( camera.parameters()["resolution"].value.x, camera.parameters()["resolution"].value.y ) )
		
		if camera.parameters()["projection"].value == "perspective" :
			f.write( ' type="perspective" fov="%f"' % camera.parameters()["projection:fov"].value )
		else :
			f.write( ' type="orthographic"' )
		
		f.write( "/>\n" )
		f.write( '</transform>\n\n' )
		
	def __walkScene( self, f, state, path ) :
	
		state = state.copy()
		state["transform"] = state["transform"] * self["in"].transform( path )
	
		object = self["in"].object( path )
		if object is not None :
			self.__writeObject( f, state, object )
			
		childNames = self["in"].childNames( path )
		for childName in childNames :
		
			childPath = path.copy()
			childPath.append( childName )
		
			self.__walkScene( f, state, childPath )
			
	def __writeObject( self, f, state, object ) :
	
		if not isinstance( object, IECore.MeshPrimitive ) :
			return
		
		f.write( '<transform matrix="' + str( state["transform"] ) + '">\n' )
		f.write( "<state>\n" )
		
		self.__writeMeshPrimitive( f, object )
		
		f.write( "</state>\n" )
		f.write( "</transform>\n\n" )
	
	def __writeMeshPrimitive( self, f, mesh ) :
	
		f.write( "<mesh\n" )
		f.write( 'P="' + str( mesh["P"].data ) + '"\n' )
		f.write( 'nverts="' + str( mesh.verticesPerFace ) + '"\n' ) 
		f.write( 'verts="' + str( mesh.vertexIds ) + '"\n' )
		if mesh.interpolation == "catmullClark" :
			f.write( 'subdivision="catmull-clark"\n' )
		f.write( "/>\n" )
	
IECore.registerRunTimeTyped( CyclesRender )

