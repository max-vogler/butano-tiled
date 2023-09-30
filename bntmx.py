"""
Copyright (c) 2023 Adrien Plazas <kekun.plazas@laposte.net>
zlib License, see LICENSE file.
"""

from PIL import Image
from tmx import MapObject, TMX
import argparse
import json
import os

def inline_c_array(l: list) -> str:
    """
    Return the inline C or C++ literal array or struct for the elements in the list.

    :param l: the list of the array elements
    :returns: the inline array literal
    """

    return "{" + ",".join(map(str, l)) + "}"

def multiline_c_array(l: list, indentation: str, depth: int) -> str:
    """
    Return the multiline C or C++ literal array or struct for the elements in the list.

    :param l: the list of the array elements
    :param indentation: the characters to use for an indentation level
    :param depth: the depth of the indentation
    :returns: the multiline array literal
    """

    outer_indentation = indentation * depth
    inner_indentation = indentation * (depth + 1)
    splitter = ",\n" + inner_indentation

    return "{\n" + inner_indentation + splitter.join(map(str, l)) + "\n" + outer_indentation + "}"

def bg_size(size: int):
    """
    Return a size rounded up to the next 256 multiple. This helps converting the
    size of a map into the size of its background images.

    :param size: the size of the map
    :returns: the size of the background that can fit the requested size
    """

    return size if size % 256 == 0 else (size // 256 + 1) * 256

class TMXConverter:
    def __init__(self, tmx_filename):
        self._tmx = TMX(tmx_filename)
        self._name = os.path.splitext(os.path.basename(tmx_filename))[0]
        descriptor = open(os.path.splitext(tmx_filename)[0] + ".json")
        self._descriptor = json.load(descriptor)

        # The list of MapObjects for the list of object layers
        self._objects = list(map(lambda layer_path: self._tmx.objects(layer_path), self._descriptor["objects"]))

    def _object_classes(self):
        # Return the sorted set of map object class names in the whole map, including the "" class

        return sorted(set([map_object_class for layer_map_objects in self._objects for map_object_class in layer_map_objects.objects().keys()]))

    def _object_classes_enum(self):
        # Return the list of enumeration definitions for the map object class names in the whole map, excluding the "" class

        return list(map(lambda i_and_object_class: i_and_object_class[1] + "=" + str(i_and_object_class[0]), enumerate(self._object_classes())))[1:]

    def _all_objects(self):
        # Return the list of map objects in the whole map

        return [map_object for layer_map_objects in self._objects for _, map_objects in layer_map_objects.objects().items() for map_object in map_objects]

    def _object_ids_enum(self):
        # Return the list of enumeration definitions for the map object ids in the whole map, excluding the None ids

        return [str(map_object.id) + "=" + str(map_object.id_value) for map_object in self._all_objects() if map_object.id is not None]

    def _object_spans(self):
        # Return a list for each layer of lists of (index,length) pairs for each
        # object of a given class in the layer, so objects can be flattened but
        # they can still be found per layer and class.

        index_lengths = []
        index = 0
        object_classes = self._object_classes()
        for layer in self._objects:
            layer_index_lengths = []
            for object_class in object_classes:
                length = len(layer.objects()[object_class]) if object_class in layer.objects() else 0
                layer_index_lengths.append((index, length))
                index = index + length
            index_lengths.append(layer_index_lengths)
        return index_lengths

    def dependencies(self):
        return self._tmx.dependencies()

    def name(self):
        # Return the name of the map

        return self._name

    def regular_bg_image(self):
        # Convert the TMX into its regular background image.

        # The size of the map, in pixels
        src_width, src_height = self._tmx.dimensions_in_pixels()
        # The size of each individual background
        bg_width, bg_height = bg_size(src_width), bg_size(src_height)

        # Compose the layers into a single background image
        n_layers = len(self._descriptor["graphics"])
        gfx_im = Image.new("RGBA", (bg_width, bg_height * n_layers), self._tmx.background_color())
        for i, layer_path in enumerate(self._descriptor["graphics"]):
            self._tmx.compose(gfx_im, layer_path, 0, bg_height * i)

        # Make the image paletted
        gfx_im = gfx_im.quantize(256)

        return gfx_im

    def regular_bg_descriptor(self):
        # Convert the TMX into its regular background descriptor.

        _, src_height = self._tmx.dimensions_in_pixels()
        bg_height = bg_size(src_height)

        descriptor = '''\
{{
    "type": "regular_bg",
    "bpp_mode": "bpp_4_auto",
    "height": {bg_height}
}}
'''.format(bg_height=bg_height)

        return descriptor

    def cpp_header(self):
        # Convert the TMX into its C++ header.

        guard = "BNTMX_MAPS_" + self._name.upper() + "_H"
        width_in_pixels, height_in_pixels = self._tmx.dimensions_in_pixels()
        width_in_tiles, height_in_tiles = self._tmx.dimensions_in_tiles()
        tile_width, tile_height = self._tmx.tile_dimensions()
        n_graphics_layers = len(self._descriptor["graphics"])
        n_objects_layers = len(self._descriptor["objects"])
        n_tiles_layers = len(self._descriptor["tiles"])
        objects = self._objects
        object_classes = multiline_c_array(self._object_classes_enum(), "    ", 3)
        object_ids = multiline_c_array(self._object_ids_enum(), "    ", 3)
        tileset_bounds = []
        for first, last, tsx in self._tmx.tilesets():
            enum_base = os.path.splitext(os.path.basename(tsx.filename()))[0].upper()
            tileset_bounds.append(enum_base + "=" + str(first))
            tileset_bounds.append(enum_base + "_LAST=" + str(last))
        tile_ids = multiline_c_array(tileset_bounds, "    ", 3)

        header = '''\
#ifndef {guard}
#define {guard}

#include "bntmx_map.h"

#include <bn_regular_bg_items_{map_name}.h>

namespace bntmx::maps
{{
    class {map_name} : public map
    {{
        public:
            enum object_class {object_classes};

            enum object_id {object_ids};

            enum tile_id {tile_ids};

            constexpr {map_name}()
            {{
            }}

            constexpr ~{map_name}()
            {{
            }}

            constexpr bn::size dimensions_in_pixels() const
            {{
                return bn::size({width_in_pixels}, {height_in_pixels});
            }}

            constexpr bn::size dimensions_in_tiles() const
            {{
                return bn::size({width_in_tiles}, {height_in_tiles});
            }}

            constexpr bn::size tile_dimensions() const
            {{
                return bn::size({tile_width}, {tile_height});
            }}

            constexpr int width_in_pixels() const
            {{
                return {width_in_pixels};
            }}

            constexpr int height_in_pixels() const
            {{
                return {height_in_pixels};
            }}

            constexpr int width_in_tiles() const
            {{
                return {width_in_tiles};
            }}

            constexpr int height_in_tiles() const
            {{
                return {height_in_tiles};
            }}

            constexpr int tile_width() const
            {{
                return {tile_width};
            }}

            constexpr int tile_height() const
            {{
                return {tile_height};
            }}

            constexpr int n_graphics_layers() const
            {{
                return {n_graphics_layers};
            }}

            constexpr int n_objects_layers() const
            {{
                return {n_objects_layers};
            }}

            constexpr int n_tiles_layers() const
            {{
                return {n_tiles_layers};
            }}

            constexpr bn::regular_bg_item regular_bg_item() const
            {{
                return bn::regular_bg_items::{map_name};
            }}

            const bntmx::map_object object(int id) const;
            const bn::span<const bntmx::map_object> objects(int objects_layer_index) const;
            const bn::span<const bntmx::map_object> objects(int objects_layer_index, int objects_class) const;
            const bn::span<const bntmx::map_tile> tiles(int tiles_layer_index) const;
    }};
}}

#endif
'''.format(guard=guard, map_name=self._name, object_classes=object_classes, object_ids=object_ids, tile_ids=tile_ids, width_in_pixels=width_in_pixels, height_in_pixels=height_in_pixels, width_in_tiles=width_in_tiles, height_in_tiles=height_in_tiles, tile_width=tile_width, tile_height=tile_height, n_graphics_layers=n_graphics_layers, n_objects_layers=n_objects_layers, n_tiles_layers=n_tiles_layers, n_objects=len(objects))

        return header

    def cpp_source(self):
        # Convert the TMX into its C++ source.

        header_filename = "bntmx_maps_" + self._name + ".h"

        width_in_tiles, height_in_tiles = self._tmx.dimensions_in_tiles()
        n_graphics_layers = len(self._descriptor["graphics"])
        n_objects_layers = len(self._descriptor["objects"])
        n_tiles_layers = len(self._descriptor["tiles"])
        size = width_in_tiles * height_in_tiles

        n_objects_classes = len(self._object_classes())
        objects_spans = multiline_c_array(map(lambda layer: multiline_c_array(map(inline_c_array, layer), "    ", 2), self._object_spans()), "    ", 1)
        flattened_objects = self._all_objects()
        n_objects = len(flattened_objects)
        # We can't have empty constexpr arrays, so let's have a dummy element
        # instead. It doesn't take much space and keeps the code more readable
        # than by dropping them.
        cpp_objects = "{bntmx::map_object(bn::fixed_point(0, 0), 0)}"
        if len(flattened_objects) > 0:
            cpp_objects = multiline_c_array(list(map(lambda i: i.cpp_object(self._name), flattened_objects)), "    ", 1)

        # Get the C or C++ array literal for the given list of tiles, matching lines and columns of the map for readability.
        tiles_to_array_literal = lambda tiles: multiline_c_array([",".join(tiles[i:i + width_in_tiles]) for i in range(0, len(tiles), width_in_tiles)], "    ", 2)
        # Get the C or C++ array literal of tiles for the given tiles layer path.
        tiles_layer_path_to_array_literal = lambda layer_path: tiles_to_array_literal(self._tmx.tiles(layer_path))
        # Get the C or C++ array literal of tiles layers for the given tiles layer paths.
        tiles = multiline_c_array(list(map(tiles_layer_path_to_array_literal, self._descriptor["tiles"])), "    ", 1)

        source = '''\
#include "{header_filename}"

#include <bn_vector.h>

namespace bntmx::maps
{{
    // Objects are sorted by layers, then within layers they are sorted by
    // classes (with classless objects first), then within classes they are
    // sorted in the order they are found.
    // Because objects IDs are assigned in the same order, they are also sorted
    // by ID.
    static constexpr bntmx::map_object _objects[] = {cpp_objects};

    // This purposefully doesn't use bn::span so we can use smaller types,
    // saving ROM space.
    static constexpr struct {{uint16_t index; uint16_t length;}} _objects_spans[{n_objects_layers}][{n_objects_classes}] = {objects_spans};

    static const bntmx::map_tile _tiles[{n_tiles_layers}][{size}] = {tiles};

    const bntmx::map_object {map_name}::object(int id) const
    {{
        BN_ASSERT(id < {n_objects}, "Invalid object ID: ", id);
        return _objects[id];
    }}

    const bn::span<const bntmx::map_object> {map_name}::objects(int objects_layer_index) const
    {{
        BN_ASSERT(objects_layer_index < {n_objects_layers}, "Invalid objects layer index: ", objects_layer_index);
        return bn::span(&_objects[_objects_spans[objects_layer_index][0].index], _objects_spans[objects_layer_index][0].length);
    }}

    const bn::span<const bntmx::map_object> {map_name}::objects(int objects_layer_index, int objects_class) const
    {{
        BN_ASSERT(objects_layer_index < {n_objects_layers}, "Invalid objects layer index: ", objects_layer_index);
        BN_ASSERT(objects_class < {n_objects_classes}, "Invalid objects class: ", objects_class);
        return bn::span(&_objects[_objects_spans[objects_layer_index][objects_class].index], _objects_spans[objects_layer_index][objects_class].length);
    }}

    const bn::span<const bntmx::map_tile> {map_name}::tiles(int tiles_layer_index) const
    {{
        BN_ASSERT(tiles_layer_index < {n_tiles_layers}, "Invalid tiles layer index: ", tiles_layer_index);
        return bn::span(_tiles[tiles_layer_index], {size});
    }}
}}
'''.format(header_filename=os.path.basename(header_filename), map_name=self._name, n_objects_layers=n_objects_layers, n_tiles_layers=n_tiles_layers, size=str(size), tiles=tiles, objects_spans=objects_spans, n_objects=n_objects, n_objects_classes=n_objects_classes, cpp_objects=cpp_objects)

        return source

def process(maps_dirs, build_dir):
    for maps_dir in maps_dirs:
        for map_file in os.listdir(maps_dir):
            if map_file.endswith('.tmx') and os.path.isfile(os.path.join(maps_dir, map_file)):
                build_graphics_dir = os.path.join(build_dir, "graphics")
                build_include_dir = os.path.join(build_dir, "include")
                build_src_dir = os.path.join(build_dir, "src")

                if not os.path.exists(build_dir):
                    os.makedirs(build_dir)
                if not os.path.exists(build_graphics_dir):
                    os.makedirs(build_graphics_dir)
                if not os.path.exists(build_include_dir):
                    os.makedirs(build_include_dir)
                if not os.path.exists(build_src_dir):
                    os.makedirs(build_src_dir)

                MapObject._next_id_value = 0

                tmx_filename = os.path.join(maps_dir, map_file)
                converter = TMXConverter(tmx_filename)
                map_name = converter.name()

                tmx_json_filename = os.path.join(maps_dir, map_name + ".json")
                bmp_filename = os.path.join(build_dir, "graphics", map_name + ".bmp")
                bmp_json_filename = os.path.join(build_dir, "graphics", map_name + ".json")
                header_filename = os.path.join(build_dir, "include", "bntmx_maps_" + map_name + ".h")
                source_filename = os.path.join(build_dir, "src", "bntmx_maps_" + map_name + ".cpp")

                # Don't rebuild unchanged files
                input_mtime = max(map(lambda filename : os.path.getmtime(filename) if os.path.isfile(filename) else 0, [tmx_filename, tmx_json_filename] + converter.dependencies()))
                output_mtime = min(map(lambda filename : os.path.getmtime(filename) if os.path.isfile(filename) else 0, [bmp_filename, bmp_json_filename, header_filename, source_filename]))
                if input_mtime < output_mtime:
                    continue

                # Export the image
                gfx_im = converter.regular_bg_image()
                gfx_im.save(bmp_filename, "BMP")

                # Export the graphics descriptor
                bmp_json = converter.regular_bg_descriptor()
                bmp_json_file = open(bmp_json_filename, "w")
                bmp_json_file.write(bmp_json)
                bmp_json_file.close()

                # Export the C++ header
                header = converter.cpp_header()
                output_file = open(header_filename, "w")
                output_file.write(header)
                output_file.close()

                # Export the C++ source
                source = converter.cpp_source()
                output_file = open(source_filename, "w")
                output_file.write(source)
                output_file.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Compile Tiled maps into code and data usable by the game engine.')
    parser.add_argument('--build', required=True, help='build directory path')
    parser.add_argument('mapsdirs', metavar='mapsdir', nargs='+',
                        help='maps directories paths')
    args = parser.parse_args()
    process(args.mapsdirs, args.build)
