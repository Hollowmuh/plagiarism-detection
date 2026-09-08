# GCP Deployment Plan

Deploy the Dual-Tier Plagiarism Detection System and Moodle LMS to Google Cloud Platform (GCP) so that it is always running and accessible via a public link.

## User Review Required

- **Ports to Open**: Open ports `8080` (Moodle), `8000` (FastAPI), and `5555` (Flower) to public traffic (`0.0.0.0/0`) on GCP to access and test them from the browser.
- **VM Size**: Use an `e2-standard-2` VM (2 vCPUs, 8 GB memory) in the `us-east1-b` zone to fit all containers (FastAPI, Redis, Postgres, Celery, Moodle) comfortably on CPU.

## Open Questions

None. The GCP CLI is authed to the project `bright-lattice-501021-m6`.

## Proposed Changes

We will perform a zero-downtime containerized deployment of the stack to Google Compute Engine. No core application files need modification, but deployment configuration files and environment settings will be set up on the remote VM.

### Infrastructure Provisioning (GCP)
1. **Firewall Rule**: Create a VPC firewall rule `allow-plagiarism-test-ports` to allow TCP traffic on ports `8000`, `8080`, and `5555`.
2. **Compute Engine VM**: Provision a VM named `plagiarism-detector-vm` running Ubuntu 22.04 LTS.
3. **Docker Installation**: Install Docker Engine and Docker Compose on the VM.

### Application Deployment
1. **Code Copying**: Archive and transfer the application codebase (`backend/`, `moodle-plugin/`, `docker-compose.yml`, `moodle-nginx.conf`) to the VM using `gcloud compute scp`.
2. **Environment Configuration**: Create a `.env` file on the VM. Crucially, set `MOODLE_URL` to `http://<VM_PUBLIC_IP>:8080` so Moodle handles redirects and resource links correctly when accessed from external browsers.
3. **Execution**: Run `docker compose up -d` to launch the stack.
4. **Data Initialization**: Execute the `setup_test_data.php` script inside the Moodle container to prepopulate the test course, assignment, and credentials.

---

## Verification Plan

### Automated/Scripted Verification
- Run the detector verification script locally on your workstation, but pointed at the VM's public IP:
  ```bash
  python verify_detector_v2.py --host <VM_PUBLIC_IP>
  ```

### Manual Verification
1. Open `http://<VM_PUBLIC_IP>:8080` in your web browser. Log in using `admin / Admin123!` or `teacher1 / Teacher123!`.
2. Open `http://<VM_PUBLIC_IP>:8000/docs` to verify the Swagger UI loads successfully.
3. Open `http://<VM_PUBLIC_IP>:5555` to verify Flower dashboard loads and registers the Celery worker.
