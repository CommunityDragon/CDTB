#version 130

in vec2 texture_coordinate;
in vec4 color;

void main() {
    float opacity = 1 - min(1, length(vec2(texture_coordinate)));
    opacity = opacity * opacity + opacity * opacity * opacity * 0.1;

    gl_FragColor = color * vec4(1,1,1, opacity);
}