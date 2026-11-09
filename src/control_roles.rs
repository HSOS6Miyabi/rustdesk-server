//! Optional native RustDesk ControlPermissions obtained from the companion OSS API.
use hbb_common::{log, tokio::{self, sync::Mutex}};
use once_cell::sync::Lazy;
use serde_derive::Deserialize;
use std::{collections::HashMap, env, time::{Duration, Instant}};

static CACHE: Lazy<Mutex<HashMap<String,(Instant,Option<u64>)>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

#[derive(Deserialize)]
struct ControlReply {
    assigned: bool,
    permissions: u64,
}

pub(crate) fn configured() -> bool {
    env::var("RUSTDESK_API_CONTROL_ROLE_URL")
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false)
}

fn cache_seconds() -> u64 {
    env::var("RUSTDESK_API_CONTROL_CACHE_SECONDS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(5)
        .min(60)
}

fn valid_bits(bits: u64) -> bool {
    if bits >> (14*2) != 0 {
        return false;
    }
    (0..14).all(|position| ((bits >> (2*position)) & 3) != 3)
}

fn parse_reply(body: &str) -> Result<Option<u64>,String> {
    let data:ControlReply=serde_json::from_str(body).map_err(|e|e.to_string())?;
    if !valid_bits(data.permissions) {
        return Err("control role contains unsupported permission states".to_owned());
    }
    Ok(if data.assigned {Some(data.permissions)} else {None})
}

async fn request(device_id: &str)->Result<Option<u64>,String>{
    let url=env::var("RUSTDESK_API_CONTROL_ROLE_URL")
        .map_err(|_|"control role URL is not configured".to_owned())?;
    if !url.starts_with("http://") && !url.starts_with("https://") {
        return Err("control role URL must use HTTP or HTTPS".to_owned());
    }
    let secret=env::var("RUSTDESK_API_INTERNAL_KEY")
        .map_err(|_|"RUSTDESK_API_INTERNAL_KEY is not set".to_owned())?;
    if secret.is_empty() {
        return Err("RUSTDESK_API_INTERNAL_KEY is empty".to_owned());
    }
    let device_id=device_id.to_owned();
    let body=tokio::task::spawn_blocking(move||{
        let client=reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(3))
            .build()
            .map_err(|err|err.to_string())?;
        let reply=client.get(url)
            .header("X-RustDesk-Internal-Key",secret)
            .query(&[("device_id",device_id)])
            .send()
            .map_err(|err|err.to_string())?;
        if !reply.status().is_success(){
            return Err(format!("control role API returned HTTP {}",reply.status()));
        }
        reply.text().map_err(|err|err.to_string())
    }).await.map_err(|err|err.to_string())??;
    parse_reply(&body)
}

// No assignment leaves the device's regular permissions untouched.
// A brief per-device cache avoids an HTTP request for every repeated
// rendezvous attempt while allowing role edits to take effect promptly.
pub(crate) async fn for_device(device_id:&str)->Option<u64>{
    if !configured()||device_id.is_empty()||device_id.len()>253 {
        return None;
    }
    let ttl=cache_seconds();
    if ttl>0{
        let cache=CACHE.lock().await;
        if let Some((created,result))=cache.get(device_id){
            if created.elapsed()<Duration::from_secs(ttl){
                return *result;
            }
        }
    }
    match request(device_id).await {
        Ok(result)=>{
            if ttl>0{
                let mut cache=CACHE.lock().await;
                if cache.len()>4096{
                    cache.retain(|_,(created,_)|created.elapsed()<Duration::from_secs(ttl));
                    if cache.len()>4096{cache.clear();}
                }
                cache.insert(device_id.to_owned(),(Instant::now(),result));
            }
            result
        }
        Err(err)=>{
            log::warn!("Unable to retrieve control role for {}: {}",device_id,err);
            None
        }
    }
}

#[cfg(test)]
mod tests{
    use super::*;

    #[test]
    fn parses_client_permission_states(){
        let keyboard_denied=1u64;
        let clipboard_allowed=2u64<<(2*2);
        let terminal_denied=1u64<<(2*6);
        let usb_allowed=2u64<<(2*13);
        let expected=keyboard_denied|clipboard_allowed|terminal_denied|usb_allowed;
        assert!(valid_bits(expected));
        let response=format!(r#"{{"assigned":true,"permissions":{expected}}}"#);
        assert_eq!(parse_reply(&response).unwrap(),Some(expected));
        assert_eq!(parse_reply(r#"{"assigned":false,"permissions":0}"#).unwrap(),None);
        assert_eq!(parse_reply(r#"{"assigned":true,"permissions":0}"#).unwrap(),Some(0));
        assert!(!valid_bits(3));
        assert!(!valid_bits(1u64<<29));
        assert!(parse_reply(r#"{"assigned":true,"permissions":3}"#).is_err());
        assert!(parse_reply("garbage").is_err());
    }
}
