import platform

def get_system_info():

    os_name = platform.system()      
    arch = platform.machine()         

    print(f"General OS: {os_name}")
    print(f"Architecture: {arch}")

    if os_name == "Linux":
        try:
           
            distro_info = platform.freedesktop_os_release()
            print(f"Distribution: {distro_info.get('NAME')} {distro_info.get('VERSION_ID')}")
        except (AttributeError, OSError):
            print("Distribution: Generic Linux (could not detect specific distro)")
    elif os_name == "Windows":
        print(f"Distribution: Windows {platform.release()}")
