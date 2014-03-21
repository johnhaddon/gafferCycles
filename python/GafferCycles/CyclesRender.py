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
import subprocess

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
				os.system( "cycles --shadingsys osl '%s'&" % fileName )
			
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
			"shadersWritten" : set(),
			"transform" : IECore.M44f(),
			"attributes" : IECore.CompoundObject(),
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
	
		state = {
			"shadersWritten" : state["shadersWritten"],
			"transform" : state["transform"] * self["in"].transform( path ),
			"attributes" : state["attributes"].copy(),
		}
		state["attributes"].update( self["in"].attributes( path ) )
	
		object = self["in"].object( path )
		if object is not None :
			self.__writeObject( f, state, object )
			
		childNames = self["in"].childNames( path )
		for childName in childNames :
		
			childPath = path.copy()
			childPath.append( childName )
		
			self.__walkScene( f, state, childPath )
	
	def __writeShader( self, f, state ) :
	
		shader = state["attributes"].get( "shader" )
		if shader is None :
			return None
	
		name = str( shader.hash() )
		if name in state["shadersWritten"] :
			return name
		
		f.write( '<shader name="%s">\n' % str( shader.hash() ) )
		
		for s in shader :
		
			handle = s.parameters.get( "__handle", None )
			handle = handle.value if handle is not None else "surface"
			shaderFile = self.__shaderFile( s )
			
			f.write( '\t<osl_shader name="%s" src="%s"' % ( handle, shaderFile ) )
			
			for parameterName, parameterValue in s.parameters.items() :
				if parameterName.startswith( "__" ) :
					continue
				if isinstance( parameterValue, IECore.StringData ) and parameterValue.value.startswith( "link:" ) :
					continue
				f.write( ' %s="%s"' % ( parameterName, str( parameterValue ) ) )
			
			f.write( ">\n" )
		
			f.write( self.__shaderParameterDefinition( shaderFile ) )
			
			f.write( '\t</osl_shader>\n' )
			
			for parameterName, parameterValue in s.parameters.items() :
				if isinstance( parameterValue, IECore.StringData ) and parameterValue.value.startswith( "link:" ) :
					fromShader, fromParameter = parameterValue.value[5:].split( "." )
					f.write( '\t<connect from="%s %s" to="%s %s"/>\n' % (
							fromShader,
							fromParameter,
							handle,
							parameterName
						)
					)
			
		f.write( '\t<connect from="surface Ci" to="output surface"/>\n' )

		f.write( '</shader>\n\n' )
	
		state["shadersWritten"].add( name )
	
		return name
			
	def __writeObject( self, f, state, object ) :
	
		if not isinstance( object, IECore.MeshPrimitive ) :
			return
		
		shaderName = self.__writeShader( f, state )
		
		f.write( '<transform matrix="' + str( state["transform"] ) + '">\n' )
		f.write( '<state' )
		if shaderName is not None :
			f.write( ' shader="%s"' % shaderName )
		f.write( '>\n' )
		
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
	
	def __shaderFile( self, shader ) :
	
		searchPath = IECore.SearchPath( os.environ["OSL_SHADER_PATHS"], ":" )
		return searchPath.find( shader.name + ".oso" )
	
	__shaderParameterDefinitions = {}
	@classmethod
	def __shaderParameterDefinition( cls, shaderFile ) :
	
		result = cls.__shaderParameterDefinitions.get( shaderFile )
		if result is not None :
			return result
		
		types = { "float", "string", "point", "vector", "normal", "color", "closure color" }
		
		result = ""
		for line in subprocess.check_output( [ "oslinfo", shaderFile ] ).split( "\n" ) :
			words = line.split()
			if not words :
				continue
				
			if words[0] == "surface" :
				result += "\t\t<output name=\"Ci\" type=\"closure color\"/>\n"
			elif words[0] == "output" :
				result += "\t\t<output name=\"%s\" type=\"%s\"/>\n" % ( words[2], words[1] )
			elif words[0] in types :
				result += "\t\t<input name=\"%s\" type=\"%s\"/>\n" % ( words[1], words[0] )
	
		cls.__shaderParameterDefinitions[shaderFile] = result
		return result
	
IECore.registerRunTimeTyped( CyclesRender )

