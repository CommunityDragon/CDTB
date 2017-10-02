#version 130

in vec2 tex;

uniform sampler2D image;

void main(){
	vec2 sample = texture(image, tex).xy * 2.0 - vec2(1.0, 1.0);
	gl_FragColor = vec4(sample, 0.0, 1.0);
}