#version 130

in vec2 tex;

uniform sampler2DRect img;

void main(){

	float len = length(texture(img, tex).xy);
	len /= 2.0;
	
	float r = min(1, len * 3.0);
	float g = min(2, len * 3.0) - 1.0;
	float b = min(3, len * 3.0) - 2.0;
	
	gl_FragColor = vec4(r, g, b, 1.0);
}