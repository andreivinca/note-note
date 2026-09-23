# The optional native text inspector (see textblocks.h), as the QML module
# the Omarchy shell loads. Build with `sh cpp/build.sh`; the module lands
# in build/NoteNote/Native/, where hosts/omarchy/TextInspector.qml imports
# it by directory. The executable links the same sources (sources.cmake)
# and registers the same types under the same name.
cmake_minimum_required(VERSION 3.21)
project(notenotetext LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Qml Quick)
include(sources.cmake)

qt_add_qml_module(notenotetext
    URI NoteNote.Native
    VERSION 1.0
    PLUGIN_TARGET notenotetext
    OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/NoteNote/Native
    SOURCES ${NOTE_NOTE_NATIVE_SOURCES}
)

target_link_libraries(notenotetext PRIVATE Qt6::Quick)
