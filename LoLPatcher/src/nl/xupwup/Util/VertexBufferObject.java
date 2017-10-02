/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.Util;

import java.nio.ByteBuffer;
import java.nio.IntBuffer;
import org.lwjgl.BufferUtils;
import static org.lwjgl.opengl.GL11.*;
import static org.lwjgl.opengl.GL15.*;

/**
 *
 * @author rick
 * 
 * WARNING: THIS CLASS WAS PORTED FROM JOGL WIHTOUT TESTING, IT MAY BE BROKEN.
 */
public class VertexBufferObject {

    private static final int sizeofFloat = 4;
    private static final int sizeofInt = 4;
    
    private int indexVBO = -1;
    private int indexVBOsize = 0;
    private final int vertexCount;
    private int vertexVBO;

    public VertexBufferObject(float[][] vert, float[][] norm, float[][] textureCoordinates) {
        vertexCount = vert.length;
        printSize(vertexCount * sizeofFloat * 8);
        genVertexVBO(vert, norm, textureCoordinates);
    }
    public VertexBufferObject(float[][] vert, float[][] norm, float[][] textureCoordinates, int[] indices) {
        vertexCount = vert.length;
        printSize(vertexCount * sizeofFloat * 8 + indices.length * sizeofInt);
        genVertexVBO(vert, norm, textureCoordinates, indices);
    }

    private void genVertexVBO(float[][] vert, float[][] norm, float[][] textureCoordinates) {
        ByteBuffer vertices = BufferUtils.createByteBuffer(vertexCount * sizeofFloat * 8);
        for (int i = 0; i < vert.length; i++) { // interleaved vbo
            vertices.putFloat(vert[i][0])
                    .putFloat(vert[i][1])
                    .putFloat(vert[i][2]); // 3 floats
            vertices.putFloat(textureCoordinates[i][0])
                    .putFloat(textureCoordinates[i][1]); // 2 floats
            vertices.putFloat(norm[i][0])
                    .putFloat(norm[i][1])
                    .putFloat(norm[i][2]); // 3 floats
        }
        vertices.flip();
        
        vertexVBO = glGenBuffers();
        glBindBuffer(GL_ARRAY_BUFFER, vertexVBO);
        glBufferData(GL_ARRAY_BUFFER, vertices, GL_STATIC_DRAW);
        //glUnmapBuffer(GL_ARRAY_BUFFER);
        glBindBuffer(GL_ARRAY_BUFFER, 0);
    }
    
    private void genVertexVBO(float[][] vert, float[][] norm, float[][] textureCoordinates, int[] indices) {
        genVertexVBO(vert, norm, textureCoordinates);
        ByteBuffer indicesb = BufferUtils.createByteBuffer(vertexCount * sizeofInt * 1);
        for(int ind : indices){
            indicesb.putInt(ind);
        }
        indicesb.flip();
        indexVBOsize = indices.length;
        indexVBO = getIndexBuffer(indicesb);
    }
    
    private int getIndexBuffer(ByteBuffer indices){
        int b = glGenBuffers();
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, b);
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices, GL_STATIC_DRAW);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
        return b;
    }
    

    public void draw(int mode) {
        vboDrawInit(indexVBO);
        vboDraw(mode);
        vboDrawExit();
    }
    public void draw(int mode, IntBuffer indices) {
        vboDrawInit(-1);
        vboDraw(mode, indices);
        vboDrawExit();
    }

    public void vboDraw(int mode, IntBuffer indices){
        glDrawElements(mode, indices);
        checkGLError();
    }
    
    public void vboDraw(int mode) {
        if(indexVBO != -1){
            glDrawElements(mode, indexVBOsize, GL_UNSIGNED_INT, 0);
        }else{
            glDrawArrays(mode, 0, vertexCount);
        }
        
        checkGLError();
    }

    public void vboDrawInit(int idxvbo) {
        glBindBuffer(GL_ARRAY_BUFFER, vertexVBO);
        
        glEnableClientState(GL_VERTEX_ARRAY);
        glVertexPointer(3, GL_FLOAT, 8 * sizeofFloat, 0);

        glEnableClientState(GL_TEXTURE_COORD_ARRAY);
        glTexCoordPointer(2, GL_FLOAT, 8 * sizeofFloat, 3 * sizeofFloat);
        
        glEnableClientState(GL_NORMAL_ARRAY);
        glNormalPointer(GL_FLOAT, 8 * sizeofFloat, 5 * sizeofFloat);
        
        if(idxvbo != -1){
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, idxvbo);
        }
        checkGLError();
    }

    public void vboDrawExit() {
        glDisableClientState(GL_VERTEX_ARRAY);
        glDisableClientState(GL_NORMAL_ARRAY);
        glDisableClientState(GL_TEXTURE_COORD_ARRAY);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
        glBindBuffer(GL_ARRAY_BUFFER, 0);
        checkGLError();
    }

    public static void printSize(int size) {
        if (size <= 1024) {
            System.out.println("Vertex buffer object size: " + size + " B");
        } else if (size > 1024 && size < 1048576) {
            System.out.println("Vertex buffer object size: " + size / 1024 + " KB");
        } else {
            System.out.println("Vertex buffer object size: " + size / 1048576 + " MB");
        }
    }

    public void destroy() {
        glDeleteBuffers(vertexVBO);
    }

    public void checkGLError() {
        int err = glGetError();
        if (err > 0) {
            try {
                throw new Exception("GL Error: " + err);
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
    }
}