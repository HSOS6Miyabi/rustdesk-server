use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

static SETTINGS_LOCK: Mutex<()> = Mutex::new(());
const DEFAULT_SETTINGS_FILE: &str = "rustdesk-server-settings.json";

#[derive(Clone, Default, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ServerSettings {
    pub relay_servers: Option<String>,
    pub always_use_relay: Option<bool>,
    pub must_login: Option<bool>,
}

pub fn settings_path() -> PathBuf {
    std::env::var_os("RUSTDESK_SERVER_SETTINGS_FILE")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(DEFAULT_SETTINGS_FILE))
}

pub fn load() -> io::Result<ServerSettings> {
    load_from(&settings_path())
}

pub fn load_from(path: &Path) -> io::Result<ServerSettings> {
    match fs::read(path) {
        Ok(data) => serde_json::from_slice(&data)
            .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err)),
        Err(err) if err.kind() == io::ErrorKind::NotFound => Ok(ServerSettings::default()),
        Err(err) => Err(err),
    }
}

pub fn update(change: impl FnOnce(&mut ServerSettings)) -> io::Result<()> {
    update_at(&settings_path(), change)
}

pub fn update_at(path: &Path, change: impl FnOnce(&mut ServerSettings)) -> io::Result<()> {
    let _lock = SETTINGS_LOCK.lock()
        .map_err(|_| io::Error::other("Server settings synchronization failed"))?;
    let mut settings = load_from(path)?;
    change(&mut settings);
    let parent = path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
    let mut file = tempfile::NamedTempFile::new_in(parent)?;
    serde_json::to_writer_pretty(file.as_file_mut(), &settings)
        .map_err(io::Error::other)?;
    file.write_all(b"\n")?;
    file.as_file_mut().sync_all()?;
    file.persist(path).map_err(|err| err.error)?;
    File::open(parent)?.sync_all()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn updates_survive_reloading_and_preserve_other_options() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("settings.json");
        assert_eq!(load_from(&path).unwrap(), ServerSettings::default());
        update_at(&path, |value| value.must_login = Some(true)).unwrap();
        update_at(&path, |value| value.always_use_relay = Some(false)).unwrap();
        update_at(&path, |value| value.relay_servers = Some("relay.example:21117".to_owned())).unwrap();
        assert_eq!(load_from(&path).unwrap(), ServerSettings {
            must_login: Some(true),
            always_use_relay: Some(false),
            relay_servers: Some("relay.example:21117".to_owned()),
        });
    }

    #[test]
    fn invalid_data_is_rejected_without_overwriting_it() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("settings.json");
        fs::write(&path, b"{invalid").unwrap();
        assert_eq!(load_from(&path).unwrap_err().kind(), io::ErrorKind::InvalidData);
        assert!(update_at(&path, |value| value.must_login = Some(true)).is_err());
        assert_eq!(fs::read(&path).unwrap(), b"{invalid");
    }

    #[test]
    fn saved_file_has_private_permissions_on_unix() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("settings.json");
        update_at(&path, |value| value.must_login = Some(false)).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(fs::metadata(path).unwrap().permissions().mode() & 0o777, 0o600);
        }
    }
}
