#version 130

in vec4 color;
#define M_PI 3.141592653

void main() {
	float percentage = color.b * color.r;
	float highlightLocation = color.g * 4;
	float ydiff = 1 - cos(M_PI * abs(color.a - 0.5) * 0.9);
	
	float diff = 1 - abs(2 + percentage - highlightLocation) / 2;
    diff = max(0, (diff * 2 - ydiff) / 2);
	
	float c = diff * diff * diff;
	
	gl_FragColor = vec4(0.5 + c * 0.3,c * 0.5 + 0.5,1,1);
}