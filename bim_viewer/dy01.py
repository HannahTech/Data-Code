import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *

view3d = UnwrapElement(IN[0])

if isinstance(view3d, View3D) and view3d.IsPerspective:
    # Extract Camera Orientation
    orientation = view3d.GetOrientation()
    
    # Converts Revit Internal Feet to Meters for WebGL (Three.js)
    eye = [round(orientation.EyePosition.X * 0.3048, 2), 
           round(orientation.EyePosition.Y * 0.3048, 2), 
           round(orientation.EyePosition.Z * 0.3048, 2)]
           
    forward_vector = orientation.ForwardDirection
    
    # Calculate target point 5 meters in front of the camera direction
    target = [round(eye[0] + forward_vector.X * 5.0, 2),
              round(eye[1] + forward_vector.Y * 5.0, 2),
              round(eye[2] + forward_vector.Z * 5.0, 2)]

    OUT = { "eye": eye, "target": target }
else:
    OUT = "Selected View is not a 3D Perspective Camera View."