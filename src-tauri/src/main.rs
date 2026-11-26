#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{net::TcpStream, sync::Mutex, thread, time::Duration};
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};
use tauri_plugin_shell::{process::CommandChild, ShellExt};
use tauri_plugin_updater::UpdaterExt;

const ADDR: &str = "127.0.0.1:8765";
const URL: &str = "http://127.0.0.1:8765";

struct Backend(Mutex<Option<CommandChild>>);

fn backend_up() -> bool {
    TcpStream::connect_timeout(&ADDR.parse().unwrap(), Duration::from_millis(300)).is_ok()
}

fn ulog(msg: &str) {
    use std::io::Write;
    let dir = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")).unwrap_or_default();
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(format!("{dir}/.nexus-ai/updater.log")) {
        let _ = writeln!(f, "{} {msg}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0));
    }
}

fn kill_backend(app: &AppHandle) {
    if let Some(child) = app.state::<Backend>().0.lock().unwrap().take() {
        let _ = child.kill();
    }
    // PyInstaller starter en barneprosess som kan bli igjen og låse nexus-backend.exe. Ta hele prosesstreet.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/IM", "nexus-backend.exe"])
            .creation_flags(0x0800_0000)
            .status();
    }
}

#[allow(dead_code)]
async fn check_update(app: AppHandle) {
    let Ok(updater) = app.updater() else { ulog("updater: kunne ikke opprettes"); return };
    let update = match updater.check().await {
        Ok(Some(u)) => { ulog(&format!("updater: ny versjon {}", u.version)); u }
        Ok(None) => { ulog("updater: ingen ny versjon"); return }
        Err(e) => { ulog(&format!("updater: feil ved sjekk: {e}")); return }
    };
    let msg = format!(
        "NEXUS AI {} er klar. Installere na? Appen starter pa nytt av seg selv.",
        update.version
    );
    let a2 = app.clone();
    let yes = tauri::async_runtime::spawn_blocking(move || {
        a2.dialog()
            .message(msg)
            .title("Oppdatering")
            .buttons(MessageDialogButtons::OkCancelCustom("Installer".into(), "Senere".into()))
            .blocking_show()
    })
    .await
    .unwrap_or(false);
    if yes {
        kill_backend(&app);
        match update.download_and_install(|_, _| {}, || {}).await {
            Ok(_) => app.restart(),
            Err(e) => ulog(&format!("updater: installasjon feilet: {e}")),
        }
    }
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            if !backend_up() {
                let (mut rx, child) = app.shell().sidecar("nexus-backend")?.env("NEXUS_VERSION", env!("CARGO_PKG_VERSION")).spawn()?;
                *app.state::<Backend>().0.lock().unwrap() = Some(child);
                tauri::async_runtime::spawn(async move { while rx.recv().await.is_some() {} });
            }
            let win = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("NEXUS AI")
                .inner_size(1360.0, 860.0)
                .min_inner_size(960.0, 620.0)
                .build()?;
            let handle = app.handle().clone();
            thread::spawn(move || {
                for _ in 0..160 {
                    if backend_up() {
                        break;
                    }
                    thread::sleep(Duration::from_millis(250));
                }
                if backend_up() {
                    let _ = win.navigate(URL.parse().unwrap());
                } else {
                    let _ = win.eval("document.getElementById('s').textContent='Backend startet ikke. Se C:\\\\Users\\\\<deg>\\\\.nexus-ai\\\\nexus.log'");
                }
                // Oppdatering styres nå av backend (automatisk nedlasting i bakgrunnen + tilbud om omstart i appen).
                let _ = &handle;
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("feil ved oppstart av NEXUS AI");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            kill_backend(handle);
        }
    });
}
