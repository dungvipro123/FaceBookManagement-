import argparse
from app.supervisor import AppSupervisor

def main():
    parser = argparse.ArgumentParser(description="FB Monitor Hunter v2.0")
    parser.add_argument("--no-tray", action="store_true", help="Chạy ở chế độ không khay hệ thống (CLI/Server-only)")
    args = parser.parse_args()

    supervisor = AppSupervisor(enable_tray=not args.no_tray)
    supervisor.run()

if __name__ == "__main__":
    main()
