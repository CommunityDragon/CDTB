#version 130

out vec2 tex;

void main() {
	gl_Position = vec4(gl_Vertex.xy, -1.0, 1.0);
	tex = max(vec2(0.0,0.0), gl_Vertex.xy * vec2(1.0,-1.0));
}