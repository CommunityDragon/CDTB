#version 130

out vec2 texture_coordinate;
out vec4 color;

void main() {
    texture_coordinate = vec2(gl_MultiTexCoord0);
    color = gl_Color;

    gl_Position = ftransform();
}