package nl.xupwup.Util;


import java.awt.Point;
import java.awt.image.BufferedImage;
import java.io.IOException;
import nl.xupwup.WindowManager.WindowManager;
import java.util.logging.Level;
import java.util.logging.Logger;
import javax.imageio.ImageIO;
import nl.xupwup.WindowManager.Component;
import nl.xupwup.WindowManager.Components.CheckBox;
import nl.xupwup.WindowManager.Components.Option;
import nl.xupwup.WindowManager.Listener;
import nl.xupwup.WindowManager.TopControls;
import nl.xupwup.WindowManager.Window;
import org.lwjgl.LWJGLException;
import org.lwjgl.input.Mouse;
import org.lwjgl.opengl.Display;
import org.lwjgl.opengl.DisplayMode;
import static org.lwjgl.opengl.GL11.*;
import static org.lwjgl.opengl.GL14.glBlendFuncSeparate;
import static org.lwjgl.opengl.GL20.*;

/**
 *
 * @author Rick Hendricksen
 */
public abstract class GLFramework extends Thread {
    public static String WINDOW_TITLE;
    double averageFrameTime = 0;
    public static Vec2d windowSize;
    public WindowManager wm;
    
    public boolean exit = false; // set to true for exit
    public TopControls topcontrols;
    public static boolean useBlur = true;
    public static boolean keepRepainting = true;
    public static boolean useFXAA = true;
    public static boolean inhibitFXAA = false;
    private boolean repaint = true;
    public boolean showFPS = true;
    boolean usetopbar = false;
    
    
    
    public FrameBuffer backBuffer = null;
    public FrameBuffer frontBuffer = null;
    public FrameBuffer applicationBuffer = null;
    
    private ShaderProgram fxaaShader;
    

    public GLFramework(String title, boolean usetopbar) {
        WINDOW_TITLE = title;
        windowSize = new Vec2d(10);
        wm = new WindowManager();
        topcontrols = new TopControls();
        this.usetopbar = usetopbar;
        if(!usetopbar){
            TopControls.height = 0;
        }
    }

    public abstract void post_glInit();
    public abstract void pre_glInit();
    public abstract void glInit();
    public abstract void draw(int w, int h);
    public abstract void resize(int w, int h);
    public abstract void onClick(int x, int y);
    public abstract void onDrag(int x, int y);
    public abstract void onRelease();
    
    @Override
    public void run() {
        pre_glInit();
        try {
            DisplayMode dispmode = new DisplayMode(600, 450);
            Display.setDisplayMode(dispmode);
            Display.setFullscreen(false);
            Display.setTitle(WINDOW_TITLE);
            Display.setResizable(false);
            Display.create();
            Display.setVSyncEnabled(true);
            Mouse.create();
            
            int w = Display.getWidth();
            int h = Display.getHeight() - TopControls.height;
            updateBuffers(w, h);
            glViewport(0, 0, w, h+TopControls.height);
            glInit();
            resize(w, h);
            windowSize = new Vec2d(w, h);
            try {
                fxaaShader = ShaderProgram.getFromStream(ClassLoader.class.getResourceAsStream("/nl/xupwup/resources/fxaa.frag"), 
                                                         ClassLoader.class.getResourceAsStream("/nl/xupwup/resources/fxaa.vert"));
            } catch (IOException ex) {
                Logger.getLogger(GLFramework.class.getName()).log(Level.SEVERE, null, ex);
            }
            
            glShadeModel(GL_SMOOTH);
            glEnable(GL_BLEND);
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
            createWindow();
            
            glInit();
            
            post_glInit();
            mainLoop();
        } catch (LWJGLException ex) {
            Logger.getLogger(GLFramework.class.getName()).log(Level.SEVERE, null, ex);
        }
    }
    
    private void createWindow(){
        final Window w = new Window(new Point(10, 10), "Global settings");
        Option o = new Option("Use blur", new Listener() {
            @Override
            public void click(Component c) {
                useBlur = ((CheckBox) c).checked;
            }
        }, null, useBlur);
        Option o3 = new Option("Use FXAA", new Listener() {
            @Override
            public void click(Component c) {
                useFXAA = ((CheckBox) c).checked;
            }
        }, null, useFXAA);
        w.addComponent(o);
        w.addComponent(o3);
        try {
            BufferedImage i = ImageIO.read(GLFramework.class.getResourceAsStream("/nl/xupwup/icons/SETTINGS_16x16-32.png"));
            topcontrols.addOption(i, "Global settings", new Listener() {
                @Override
                public void click(Component c) {
                    if(wm.hasFocus(w)){
                        wm.closeWindow(w);
                    }else{
                        wm.addWindow(w);
                    }
                }
            });
        } catch (IOException ex) {
            Logger.getLogger(GLFramework.class.getName()).log(Level.SEVERE, null, ex);
        }
    }
    
    private void updateBuffers(int w, int h){
        if(backBuffer != null){
            backBuffer.destroy();
        }
        if(frontBuffer != null){
            frontBuffer.destroy();
        }
        if(applicationBuffer != null){
            applicationBuffer.destroy();
        }
        backBuffer = new FrameBuffer(w, h);
        frontBuffer = new FrameBuffer(w, h);
        applicationBuffer = new FrameBuffer(w, h);
    }
    
    private long framecounter = 0;
    private boolean mouseWasdown;
    private boolean wmActive = false;
    
    private void mainLoop() {
        while (!Display.isCloseRequested() && !exit) {
            if (Display.wasResized()) {
                int w = Display.getWidth();
                int h = Display.getHeight() - TopControls.height;
                
                updateBuffers(w, h);
                
                windowSize = new Vec2d(w, h);
                resize(w, h);
            }
            long starttime = System.currentTimeMillis();
            
            if(keepRepainting && repaint){
                repaint = false;
                applicationBuffer.bind();
                glLoadIdentity();
                glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
                draw((int) windowSize.x, (int) windowSize.y);
            }
            backBuffer.bind();
            glColor3f(1, 1, 1);
            if(useFXAA && !inhibitFXAA){
                fxaaShader.enable();
                glUniform2f(fxaaShader.getUniformLocation("texcoordOffset"), 
                        1f / applicationBuffer.xsize, 1f / applicationBuffer.ysize);
            }
            glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE);
            applicationBuffer.drawBuffer();
            if(useFXAA){
                fxaaShader.disable();
            }
            

            boolean mouse = Mouse.isButtonDown(0);
            if (mouse) {
                if (!mouseWasdown) {
                    if(Display.getHeight() - Mouse.getY() <= TopControls.height && usetopbar){
                        topcontrols.click(Mouse.getX());
                    }else if (wm.click(Mouse.getX(), Display.getHeight() - Mouse.getY() - TopControls.height)) {
                        wmActive = true;
                    } else {
                        wmActive = false;
                        onClick(Mouse.getX(), Mouse.getY());
                    }
                } else {
                    if(Display.getHeight() - Mouse.getY() <= TopControls.height && usetopbar){
                        if (wmActive) {
                            wm.release();
                            wmActive = false;
                        } else {
                            onRelease();
                        }
                    }else if (wmActive) {
                        wm.drag(Mouse.getX(), Display.getHeight() - Mouse.getY() - TopControls.height);
                    } else {
                        onDrag(Mouse.getX(), Mouse.getY());
                    }
                }
            } else {
                if (wmActive) {
                    wm.release();
                    wmActive = false;
                } else {
                    onRelease();
                }
            }
            mouseWasdown = mouse;

            wm.draw(frontBuffer, backBuffer);
            
            backBuffer.unbind();
            glLoadIdentity();
            glClearColor(0.0f, 0.0f, 0.0f, 1);
            glColor3f(1, 1, 1);
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
            glViewport(0, 0, Display.getWidth(), Display.getHeight() - TopControls.height);
            backBuffer.drawBuffer();
            if(usetopbar){
                glViewport(0, Display.getHeight() - TopControls.height, Display.getWidth(), TopControls.height);
                topcontrols.draw(Display.getWidth(), (Display.getHeight() - Mouse.getY() <= TopControls.height ? Mouse.getX() : 0));
            }
            if (framecounter++ % 10 == 0 && showFPS) {
                Display.setTitle(WINDOW_TITLE + " " + RoundFloat.round(averageFrameTime, 1)
                        + "ms/frame");
            }
            Display.update();
            long frametime = System.currentTimeMillis() - starttime;
            averageFrameTime = (10 * averageFrameTime + frametime) / 11;
            
            Display.sync(60);
        }
        onClose();
    }
    
    public void repaint(){
        repaint = true;
    }

    
    public abstract void onClose();
}
