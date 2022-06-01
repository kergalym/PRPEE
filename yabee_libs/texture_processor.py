""" Part of the YABEE
"""

import bpy
import shutil

if __name__ != '__main__':
    from .utils import convertFileNameToPanda, save_image


class PbrTextures:
    def __init__(self, obj_list, uv_img_as_texture, copy_tex, file_path, tex_path):
        self.obj_list = obj_list[:]
        self.uv_img_as_texture = uv_img_as_texture
        self.copy_tex = copy_tex
        self.file_path = file_path
        self.tex_path = tex_path

    def get_used_textures(self):
        """ Collect images from the UV images and Material texture slots
            tex_list structure:
            image_name: { 'scalars': [(name, val), (name, val), ...],
                          'path': 'path/to/texture',
                          'transform': [(type, val), (type, val), ...]
                        }
        """
        tex_list = {}
        print(self.obj_list)
        for obj in self.obj_list:
            if obj.type == 'MESH':
                print("Processing object", obj)
                # General textures
                handled = set()
                for f in obj.data.polygons:
                    # print("processing polygon", f)
                    if f.material_index < len(obj.data.materials):
                        # print("found material index")
                        mat = obj.data.materials[f.material_index]
                        if not mat or mat in handled:
                            continue

                        handled.add(mat)

                        nodeNames = {"Base Color": None,
                                     "Specular": None,
                                     "Roughness": None,
                                     "Normal": None}

                        # let's crawl all links, find the ones connected to the PandaPBRNode,
                        # find the connected textures, use them.
                        for link in mat.node_tree.links:
                            # if the link connects to the Panda3D compatible node

                            if link.to_node.name == "Principled BSDF":
                                print("INFO: Found the Panda3D compatible Principled BSDF shader")
                                # and it connects to one of our known sockets...

                                if link.to_socket.name in nodeNames.keys():
                                    textureNode = link.from_node

                                    # If normal map texture is connected through NormalMap node
                                    # (we need it to get strength for RenderPipeline)
                                    if not hasattr(textureNode, 'image'):
                                        if textureNode.type == "NORMAL_MAP":
                                            if (link.from_node.name == "Normal Map"
                                                    and link.from_node.inputs[1].is_linked):
                                                print("INFO: Texture node assigned through NormalMap node.",
                                                      obj.name, link.from_node.name)

                                                textureNode = link.from_node.inputs[1].links[0].from_node

                                    # If normal map texture is connected directly
                                    if hasattr(textureNode, 'image'):
                                        if not textureNode.image:
                                            print("WARNING: Texture node has no image assigned!", obj.name,
                                                  link.to_socket.name)

                                        scalars = []

                                        imageNode = bpy.data.images[textureNode.image.name]

                                        if (link.to_socket.name == 'Base Color'
                                                and link.to_node.inputs[0].is_linked):
                                            if imageNode.colorspace_settings.name == "sRGB":
                                                scalars.append(('format', 'srgb'))

                                            scalars.append(('envtype', 'modulate'))

                                        elif (link.to_socket.name == 'Normal'
                                              and link.from_node.outputs[0].is_linked):

                                            if imageNode.colorspace_settings.name == "Non-Color":
                                                scalars.append(('format', 'rgb'))

                                            scalars.append(('envtype', 'normal'))

                                        # Make unique named Image Texture node by assigning the texture name
                                        # so we can use multiple textures for multimeshed object
                                        if textureNode.name:
                                            textureNode.name = textureNode.image.name
                                            print("INFO: {} node is renamed to {}".format(textureNode.name,
                                                                                          textureNode.image.name))

                                        if (not textureNode.inputs[0].is_linked
                                                and textureNode.image):
                                            print("WARNING: Texture has no UV-INPUT!", obj.name,
                                                  link.to_socket.name)
                                            print("INFO: Adding UV Map from the material:", obj.name)
                                            a = [uv for uv in obj.data.uv_layers if uv.active]
                                            uv_map = [x.name for x in a]
                                            scalars.append(('uv-name', uv_map.pop()))

                                        # we have to crawl the links again
                                        # we finally found the uv-map connected to the texture we want
                                        # or we take it from the material
                                        for link2 in mat.node_tree.links:
                                            if link2.to_node == textureNode:
                                                uvNode = link2.from_node
                                                if hasattr(uvNode, 'uv_map'):
                                                    scalars.append(('uv-name', uvNode.uv_map))
                                                else:
                                                    a = [uv for uv in obj.data.uv_layers if uv.active]
                                                    uv_map = [x.name for x in a]
                                                    scalars.append(('uv-name', uv_map.pop()))

                                        t_path = textureNode.image.filepath
                                        if textureNode.image and self.copy_tex:
                                            t_path = save_image(textureNode.image, self.file_path, self.tex_path)

                                        transform = []

                                        if textureNode.interpolation == "Linear":
                                            scalars.append(('minfilter', 'linear_mipmap_linear'))
                                            scalars.append(('magfilter', 'linear'))

                                        # Process wrap modes.
                                        if textureNode.extension == 'EXTEND':
                                            scalars.append(('wrap', 'clamp'))

                                        elif textureNode.extension == 'REPEAT':
                                            scalars.append(('wrapu', 'repeat'))
                                            scalars.append(('wrapv', 'repeat'))

                                        # Alpha blending modes for texture
                                        if bpy.context.object.active_material.blend_method == "OPAQUE":
                                            scalars.append(('alpha', 'off'))
                                        elif bpy.context.object.active_material.blend_method == "CLIP":
                                            scalars.append(('alpha', 'binary'))
                                        elif bpy.context.object.active_material.blend_method == "HASHED":
                                            scalars.append(('alpha', 'ms'))
                                        elif bpy.context.object.active_material.blend_method == "BLEND":
                                            scalars.append(('alpha', 'blend'))

                                        # Process coordinate mapping using a matrix.
                                        mappings = (
                                            textureNode.texture_mapping.mapping_x,
                                            textureNode.texture_mapping.mapping_y,
                                            textureNode.texture_mapping.mapping_z)

                                        if mappings != ('X', 'Y', 'Z'):
                                            matrix = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]

                                            for col, mapping in enumerate(mappings):
                                                if mapping == 'Z':
                                                    # Z is not present when using UV coordinates.
                                                    # We always use uv for pbr so far
                                                    mapping = 'NONE'

                                                if mapping == 'NONE':
                                                    # It seems that Blender sets Z to 0.5 when it is not present.
                                                    matrix[4 * 3 + col] = 0.5
                                                else:
                                                    row = ord(mapping) - ord('X')
                                                    matrix[4 * row + col] = 1

                                            transform.append(('Matrix4', matrix))

                                        # Process texture transformations.
                                        if tuple(textureNode.texture_mapping.scale) != (1.0, 1.0, 1.0):
                                            # Blender scales from the centre, so shift it
                                            # before scaling and then shift it back.
                                            transform.append(('Translate', (-0.5, -0.5, -0.5)))
                                            transform.append(('Scale', textureNode.texture_mapping.scale))
                                            transform.append(('Translate', (0.5, 0.5, 0.5)))

                                        if tuple(textureNode.texture_mapping.translation) != (0.0, 0.0, 0.0):
                                            transform.append(('Translate', textureNode.texture_mapping.translation))

                                        # finally add everything to the list
                                        tex_list[textureNode.name] = {'path': t_path,
                                                                      'scalars': scalars, 'transform': transform}
                                else:
                                    print("WARNING: The Panda3D compatible Principled BSDF shader not found. "
                                          "Texture was not exported!")

        return tex_list


if __name__ == '__main__':
    import os


    def convertFileNameToPanda(filename):
        """ (Get from Chicken) Converts Blender filenames to Panda 3D filenames.
      """
        path = filename.replace('//', './').replace('\\', '/')
        if os.name == 'nt' and path.find(':') != -1:
            path = '/{}{}'.format(path[0].lower(), path[2:])
        return path


    def save_image(img, file_path, text_path):
        oldpath = bpy.path.abspath(img.filepath)
        old_dir, old_f = os.path.split(convertFileNameToPanda(oldpath))
        f_names = [s.lower() for s in old_f.split('.')]
        if not f_names[-1] in ('jpg', 'png', 'tga', 'tiff', 'dds', 'bmp') and img.is_dirty:
            old_f += ('.' + bpy.context.scene.render.image_settings.file_format.lower())
        rel_path = os.path.join(text_path, old_f)
        if os.name == 'nt':
            rel_path = rel_path.replace('\\', '/')
        new_dir, eg_f = os.path.split(file_path)
        new_dir = os.path.abspath(os.path.join(new_dir, text_path))
        if not os.path.exists(new_dir):
            os.makedirs(new_dir)
        if img.is_dirty:
            r_path = os.path.abspath(os.path.join(new_dir, old_f))
            img.save_render(r_path)
            print('RENDER IMAGE to %s; rel path: %s' % (r_path, rel_path))
        else:
            if os.path.exists(oldpath):
                # oldf = convertFileNameToPanda(oldpath)
                newf = os.path.join(new_dir, old_f)
                if oldpath != newf:
                    shutil.copyfile(oldpath, newf)
                    print('COPY IMAGE %s to %s; rel path %s' % (oldpath, newf, rel_path))
            else:
                if img.has_data:
                    img.filepath = os.path.abspath(os.path.join(new_dir, old_f))
                    print('SAVE IMAGE to %s; rel path: %s' % (img.filepath, rel_path))
                    img.save()
                    img.filepath == oldpath
        return rel_path
