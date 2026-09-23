cmake_minimum_required(VERSION 3.21)
# manifest.json is the one place the version is written; the executable,
# the build info and the packager all read it from here.
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/manifest.json" NOTE_NOTE_MANIFEST)
string(JSON NOTE_NOTE_VERSION GET "${NOTE_NOTE_MANIFEST}" version)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS manifest.json)
project(NoteNote VERSION ${NOTE_NOTE_VERSION} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
include(GNUInstallDirs)
include(CTest)
find_package(Qt6 6.8 REQUIRED COMPONENTS Quick QuickControls2 Network DBus)
configure_file(packaging/build-info.json.in note-note-build.json @ONLY)
file(RELATIVE_PATH NOTE_NOTE_DATA_FROM_BIN "${CMAKE_INSTALL_FULL_BINDIR}" "${CMAKE_INSTALL_FULL_DATADIR}/note-note")

add_library(note-note-theme STATIC
    hosts/standalone/theme/palette.cpp hosts/standalone/theme/palette.h
    hosts/standalone/theme/portalsettings.cpp hosts/standalone/theme/portalsettings.h
    hosts/standalone/theme/desktoptheme.cpp hosts/standalone/theme/desktoptheme.h)
target_link_libraries(note-note-theme PUBLIC Qt6::Gui Qt6::DBus)

add_executable(note-note
    hosts/standalone/main.cpp
    hosts/standalone/runtime.cpp hosts/standalone/runtime.h
    hosts/standalone/processbackend.cpp hosts/standalone/processbackend.h
    cpp/dialect.h cpp/textblocks.cpp cpp/textblocks.h cpp/textlinks.cpp cpp/textlinks.h
)
target_link_libraries(note-note PRIVATE Qt6::Quick Qt6::QuickControls2 Qt6::Network note-note-theme)
# The executable knows its resources by their place next to it and by the
# install prefix, never by the tree it was built from: a release binary
# carries nothing about the build machine, and a build-tree run names the
# source tree with `--data-dir`.
target_compile_definitions(note-note PRIVATE
    NOTE_NOTE_VERSION="${PROJECT_VERSION}"
    NOTE_NOTE_DATA_FROM_BIN="${NOTE_NOTE_DATA_FROM_BIN}"
    NOTE_NOTE_INSTALL_DATA_DIR="${CMAKE_INSTALL_FULL_DATADIR}/note-note"
)
install(TARGETS note-note RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES Workspace.qml LICENSE NOTICE.md DESTINATION ${CMAKE_INSTALL_DATADIR}/note-note)
# Runtime data is installed by what it is: the QML, scripts and logos the
# application loads, the fonts, and the licences and notes of what is
# vendored. A source file, a test or a build product in these trees is not
# a runtime file and stays out by that alone; the two directory excludes are
# for generated trees whose contents would otherwise match.
install(DIRECTORY assets design ui providers services lib
    DESTINATION ${CMAKE_INSTALL_DATADIR}/note-note
    FILES_MATCHING
    PATTERN "__pycache__" EXCLUDE
    PATTERN "graphify-out" EXCLUDE
    PATTERN "*selftest*" EXCLUDE
    PATTERN "*.qml" PATTERN "*.js" PATTERN "*.py" PATTERN "qmldir"
    PATTERN "*.svg" PATTERN "*.ttf" PATTERN "*.otf"
    PATTERN "*.md" PATTERN "LICENSE*" PATTERN "COPYING*")
install(FILES hosts/standalone/Main.qml hosts/standalone/Backend.qml hosts/standalone/TextInspector.qml
    DESTINATION ${CMAKE_INSTALL_DATADIR}/note-note/hosts/standalone)
install(FILES packaging/desktop/io.github.andreivinca.note-note.desktop DESTINATION ${CMAKE_INSTALL_DATADIR}/applications)
install(FILES packaging/desktop/io.github.andreivinca.note-note.metainfo.xml DESTINATION ${CMAKE_INSTALL_DATADIR}/metainfo)
install(FILES packaging/desktop/io.github.andreivinca.note-note.svg DESTINATION ${CMAKE_INSTALL_DATADIR}/icons/hicolor/scalable/apps)

if(BUILD_TESTING)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    find_package(Qt6 6.8 REQUIRED COMPONENTS Test)
    find_program(DBUS_RUN_SESSION dbus-run-session REQUIRED)
    add_executable(theme-test tests/theme_test.cpp)
    target_link_libraries(theme-test PRIVATE Qt6::Test note-note-theme)
    add_test(NAME theme COMMAND ${DBUS_RUN_SESSION} -- $<TARGET_FILE:theme-test>)
    set_tests_properties(theme PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QPA_PLATFORMTHEME=generic" TIMEOUT 60)
    add_executable(native-runtime-test tests/native_runtime_test.cpp
        hosts/standalone/runtime.cpp hosts/standalone/runtime.h)
    target_link_libraries(native-runtime-test PRIVATE Qt6::Test Qt6::Gui)
    add_test(NAME native-runtime COMMAND native-runtime-test)
    set_tests_properties(native-runtime PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QPA_PLATFORMTHEME=generic")
    add_test(NAME standalone COMMAND ${Python3_EXECUTABLE}
        ${CMAKE_CURRENT_SOURCE_DIR}/tests/standalone_selftest.py $<TARGET_FILE:note-note>)
    add_test(NAME native-transitions COMMAND ${Python3_EXECUTABLE}
        ${CMAKE_CURRENT_SOURCE_DIR}/tests/transition_selftest.py --standalone)
    set_tests_properties(native-transitions PROPERTIES
        ENVIRONMENT "NOTE_NOTE_BINARY=$<TARGET_FILE:note-note>" TIMEOUT 240)
endif()
