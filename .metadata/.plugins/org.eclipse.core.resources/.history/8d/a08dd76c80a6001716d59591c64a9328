#version 130

uniform sampler2DRect source;
uniform vec2 cursor;

const int kernel = 1;
const float neighborInfluence = 0.20;
const float friction = 0.34;


void main(){
	vec2 tex = gl_FragCoord.xy;
	
	vec2 sumDir = vec2(0,0);
	for(int i = -kernel; i <= kernel; i++ ){
		for(int j = -kernel; j <= kernel; j++ ){
			if(i == 0 && j == 0) continue;
			
			vec2 dir1 = -normalize(vec2(i,j));
			
			vec2 sample = texture(source, tex + vec2(i,j)).xy;
			
			float len = length(sample);
			if(len > 0.0){
				float factor = clamp(dot((sample / len), dir1), 0.0, 1.0);
				factor = factor * factor;
				
				
				sumDir += sample * factor * neighborInfluence / length(vec2(i,j));
			}
		}
	}
	
	
	vec2 sampleSelf = texture(source, tex).xy;
	vec2 finalOut = sampleSelf * (1.0 - friction) + sumDir;
	
	
	vec2 distToCursor = tex - cursor;
	
	if(length(distToCursor) < 10.0 && length(distToCursor) > 5.0){
		finalOut += normalize(distToCursor);
	}
	
	
	gl_FragColor = vec4(finalOut, 0.0, 1.0);
}