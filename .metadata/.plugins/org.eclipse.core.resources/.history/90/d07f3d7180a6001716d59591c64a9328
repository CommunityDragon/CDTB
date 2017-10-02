#version 130

out vec4 vertColor;
out vec2 vertTexcoord;

void main() {
    vertColor = gl_Color;
    vertTexcoord = vec2(gl_MultiTexCoord0);
    
    gl_Position = ftransform();
} 
