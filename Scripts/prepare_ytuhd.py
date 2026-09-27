#!/usr/bin/env python3
"""Prepare YTUHD tweak for building in uYouEnhanced.

Fixes:
1. Submodules: Ensures vendor/libvpx and vendor/dav1d submodules are checked out.
2. Include & script paths: Replaces $(THEOS_PROJECT_DIR)/vendor with $(CURDIR)/vendor
   in Tweaks/YTUHD/Makefile so it resolves to the YTUHD directory instead of the
   top-level uYouEnhanced project directory during aggregate make builds.
3. Build ordering: Adds before-all:: $(LIBVPX_A) $(DAV1D_A) so static libraries
   are compiled before any object files.
4. SDK & environment fallbacks: Patches build_libvpx.sh and build_dav1d.sh to handle
   SDK_PATH/SYSROOT when xcrun is not configured or in custom environments.
"""

import os
import stat
import subprocess
import sys

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ytuhd_dir = os.path.join(root_dir, "Tweaks", "YTUHD")

    if not os.path.isdir(ytuhd_dir):
        print(f"[prepare_ytuhd] YTUHD directory not found at {ytuhd_dir}, skipping.")
        return 0

    print("[prepare_ytuhd] Preparing YTUHD for compilation...")

    # 1. Ensure nested submodules in Tweaks/YTUHD are populated
    print("[prepare_ytuhd] Updating nested submodules (vendor/libvpx, vendor/dav1d)...")
    subprocess.run(
        ["git", "submodule", "update", "--init", "--recursive", "Tweaks/YTUHD"],
        cwd=root_dir,
        check=False
    )

    # 2. Patch Tweaks/YTUHD/Makefile
    ytuhd_makefile = os.path.join(ytuhd_dir, "Makefile")
    if os.path.isfile(ytuhd_makefile):
        with open(ytuhd_makefile, "r", encoding="utf-8") as f:
            content = f.read()

        orig_content = content

        # Replace $(THEOS_PROJECT_DIR)/vendor with $(CURDIR)/vendor
        content = content.replace("$(THEOS_PROJECT_DIR)/vendor", "$(CURDIR)/vendor")

        # Ensure before-all dependency rule exists
        if "before-all:: $(LIBVPX_A) $(DAV1D_A)" not in content:
            # Insert before-all rule before include $(THEOS_MAKE_PATH)/tweak.mk
            target = "include $(THEOS_MAKE_PATH)/tweak.mk"
            if target in content:
                content = content.replace(
                    target,
                    "before-all:: $(LIBVPX_A) $(DAV1D_A)\n"
                    "$(THEOS_OBJ_DIR)/YTUHD.dylib: $(LIBVPX_A) $(DAV1D_A)\n\n"
                    + target
                )
            else:
                content += "\nbefore-all:: $(LIBVPX_A) $(DAV1D_A)\n$(THEOS_OBJ_DIR)/YTUHD.dylib: $(LIBVPX_A) $(DAV1D_A)\n"

        if content != orig_content:
            with open(ytuhd_makefile, "w", encoding="utf-8") as f:
                f.write(content)
            print("[prepare_ytuhd] Successfully patched Tweaks/YTUHD/Makefile")
        else:
            print("[prepare_ytuhd] Tweaks/YTUHD/Makefile already patched")

    # 3. Patch build_libvpx.sh and build_dav1d.sh for SDK fallbacks and execution
    vendor_dir = os.path.join(ytuhd_dir, "vendor")
    libvpx_sh = os.path.join(vendor_dir, "build_libvpx.sh")
    dav1d_sh = os.path.join(vendor_dir, "build_dav1d.sh")

    sdk_fallback_snippet = '''SDK="$(xcrun --sdk iphoneos --show-sdk-path 2>/dev/null || true)"
if [ -z "$SDK" ] || [ ! -d "$SDK" ]; then
    if [ -n "$SDK_PATH" ] && [ -d "$SDK_PATH" ]; then
        SDK="$SDK_PATH"
    elif [ -n "$SYSROOT" ] && [ -d "$SYSROOT" ]; then
        SDK="$SYSROOT"
    elif [ -n "$THEOS" ] && [ -d "$THEOS/sdks" ]; then
        SDK="$(ls -d "$THEOS/sdks"/iPhoneOS*.sdk 2>/dev/null | head -n 1)"
    fi
fi
'''

    if os.path.isfile(libvpx_sh):
        # Make executable
        st = os.stat(libvpx_sh)
        os.chmod(libvpx_sh, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        with open(libvpx_sh, "r", encoding="utf-8") as f:
            c = f.read()
        orig_c = c
        if 'SDK="$(xcrun --sdk iphoneos --show-sdk-path)"' in c:
            c = c.replace('SDK="$(xcrun --sdk iphoneos --show-sdk-path)"', sdk_fallback_snippet)
        if 'sysctl -n hw.ncpu' in c and 'nproc' not in c:
            c = c.replace('$(sysctl -n hw.ncpu)', '$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)')
        if c != orig_c:
            with open(libvpx_sh, "w", encoding="utf-8") as f:
                f.write(c)
            print("[prepare_ytuhd] Patched vendor/build_libvpx.sh")

    if os.path.isfile(dav1d_sh):
        # Make executable
        st = os.stat(dav1d_sh)
        os.chmod(dav1d_sh, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        with open(dav1d_sh, "r", encoding="utf-8") as f:
            c = f.read()
        orig_c = c
        if 'SDK="$(xcrun --sdk iphoneos --show-sdk-path)"' in c:
            c = c.replace('SDK="$(xcrun --sdk iphoneos --show-sdk-path)"', sdk_fallback_snippet)
        if 'sysctl -n hw.ncpu' in c and 'nproc' not in c:
            c = c.replace('$(sysctl -n hw.ncpu)', '$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)')
        if 'find "$BUILD_DIR/install" -name "libdav1d.a"' not in c and 'cp "$BUILD_DIR/install/lib/libdav1d.a" "$BUILD_DIR/libdav1d.a"' in c:
            c = c.replace(
                'cp "$BUILD_DIR/install/lib/libdav1d.a" "$BUILD_DIR/libdav1d.a"',
                'cp "$BUILD_DIR"/install/lib*/libdav1d.a "$BUILD_DIR/libdav1d.a" 2>/dev/null || '
                'find "$BUILD_DIR/install" -name "libdav1d.a" -exec cp -f {} "$BUILD_DIR/libdav1d.a" \\; 2>/dev/null || '
                'cp "$BUILD_DIR/install/lib/libdav1d.a" "$BUILD_DIR/libdav1d.a"'
            )
        if c != orig_c:
            with open(dav1d_sh, "w", encoding="utf-8") as f:
                f.write(c)
            print("[prepare_ytuhd] Patched vendor/build_dav1d.sh")

    print("[prepare_ytuhd] Done.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
