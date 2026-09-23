# The native text inspector's sources, named once: the optional QML module
# the Omarchy shell loads (cpp/CMakeLists.txt) and the executable that links
# them in (CMakeLists.txt at the root) are two builds of the one definition.
set(NOTE_NOTE_NATIVE_SOURCES
    ${CMAKE_CURRENT_LIST_DIR}/dialect.h
    ${CMAKE_CURRENT_LIST_DIR}/textblocks.h ${CMAKE_CURRENT_LIST_DIR}/textblocks.cpp
    ${CMAKE_CURRENT_LIST_DIR}/textlinks.h ${CMAKE_CURRENT_LIST_DIR}/textlinks.cpp)
