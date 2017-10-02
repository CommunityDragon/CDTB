#version 130

in vec2 texture_coordinate;
in vec4 color;
uniform sampler2D tex;
uniform int winx;
uniform int winy;
uniform int topbarh;
const int samples = 5;
const int hsamples = 2;

void main() {
    vec2 pixel = vec2(1.0/ winx, 1.0/winy);
    
    vec2 fragCoord = gl_FragCoord.xy;
    fragCoord.x /= winx;
    fragCoord.y /= winy - topbarh;
    
    
    vec4 col = vec4(0,0,0,0);
    
    for(int i = 0; i < samples; i++){
        float x = fragCoord.x + (i - hsamples) * pixel.x;
        x = min(1.0, max(0.0, x));
        for(int j = 0; j < samples; j++){
            float y = fragCoord.y + (j - hsamples) * pixel.y;
            y = min(1.0, max(0.0, y));

            col += texture2D(tex, vec2(x,y));
        }
    }
    col /= samples * samples;
    col.a = 1;
    gl_FragColor = col * 0.3 + color * 0.7;
}