/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.Util;

/**
 *
 * @author rick
 */
public final class Vec3d {
    final public double x;
    final public double y;
    final public double z;
    
    public Vec3d(double x, double y, double z){
        this.x = x;
        this.y = y;
        this.z = z;
    }
    public Vec3d(double v){
        this.x = (this.y = (this.z = v));
    }
    public Vec3d(){
        x = (y = (z = 0));
    }
    
    public double length(){
        return Math.sqrt(x * x + y * y + z * z);
    }
    
    public Vec3d multiply(double f){
        return new Vec3d(x * f, y * f, z * f);
    }
    /**
     * component wise multiplication
     * @param v
     * @return 
     */
    public Vec3d multiply(Vec3d v){
        return new Vec3d(x * v.x, y * v.y, z * v.z);
    }
    
    public Vec3d div(double f){
        return new Vec3d(x / f, y / f, z / f);
    }
    /**
     * component wise division
     * @param v
     * @return 
     */
    public Vec3d div(Vec3d v){
        return new Vec3d(x / v.x, y / v.y, z / v.z);
    }
    
    public Vec3d add(Vec3d v){
        return new Vec3d(x + v.x, y + v.y, z + v.z);
    }
    public Vec3d add(double d){
        return new Vec3d(x + d, y + d, z + d);
    }
    
    public Vec3d minus(Vec3d v){
        return new Vec3d(x - v.x, y - v.y, z - v.z);
    }
    public Vec3d minus(double d){
        return new Vec3d(x - d, y - d, z - d);
    }
    public double dot(Vec3d v){
        return x * v.x + y * v.y + z * v.z;
    }
    
    public Vec3d normalized(){
        double l = length();
        if(l == 0){
            return new Vec3d();
        }else return div(l);
    }
    
    public boolean equals(Vec3d v){
        return v.x == x && v.y == y && v.z == z;
    }
    
    public double distSQ(Vec3d v){
        double xd = v.x - x;
        double yd = v.y - y;
        return xd * xd + yd * yd;
    }
    
    public Vec3d cross(Vec3d v) {
        double xx = y * v.z - z * v.y;
        double yy = z * v.x - x * v.z;
        double zz = x * v.y - y * v.x;
        return new Vec3d(xx, yy, zz);
    }
    
    /**
     * Projects this vector onto vector "on".
     * @param on
     * @return 
     */
    public Vec3d project(Vec3d on){
        return on.multiply(dot(on) / on.dot(on));
    }
    
    @Override
    public String toString(){
        return "(" + x + ", " + y + ", " + z + ")";
    }
}