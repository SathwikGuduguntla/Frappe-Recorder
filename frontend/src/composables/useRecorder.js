import { ref } from "vue";
import { createResource } from "frappe-ui";

export function useRecorder() {
  const isRecording = ref(false);
  const isUploading = ref(false);
  
  let mediaRecorder = null;
  let chunks = [];
  let startedAt = 0;
  
  // Cache parameters to make them available across function scopes
  let currentTitle = "";
  let currentFolder = null;

  // Updated backend whitelisted resource paths pointing to the DocType controller
  const createRecordingDoc = createResource({
    url: "frappe_recorder.frappe_recorder.doctype.screen_recording.screen_recording.create_recording",
  });

  const finalizeRecordingDoc = createResource({
    url: "frappe_recorder.frappe_recorder.doctype.screen_recording.screen_recording.finalize_recording",
  });

  async function start(title, folder = null, includeMic = true) {
    chunks = [];
    currentTitle = title;
    currentFolder = folder;
    
    try {
      const screenStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: true,
      });
      
      let combinedStream = screenStream;

      if (includeMic) {
        try {
          const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          const audioCtx = new AudioContext();
          const dest = audioCtx.createMediaStreamDestination();
          
          audioCtx.createMediaStreamSource(screenStream).connect(dest);
          audioCtx.createMediaStreamSource(micStream).connect(dest);
          
          combinedStream = new MediaStream([
            ...screenStream.getVideoTracks(),
            ...dest.stream.getAudioTracks(),
          ]);
        } catch (e) {
          console.warn("Microphone unavailable, recording system audio only.");
        }
      }

      mediaRecorder = new MediaRecorder(combinedStream, {
        mimeType: "video/webm;codecs=vp9,opus",
      });

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      };

      // Auto stop if user clicks the native browser "Stop Sharing" floating bar
      screenStream.getVideoTracks()[0].onended = () => stop();

      startedAt = Date.now();
      mediaRecorder.start();
      isRecording.value = true;
    } catch (err) {
      console.error("Error accessing media capture layers:", err);
      alert("Could not start recording: " + err.message);
    }
  }

  async function stop() {
    if (!mediaRecorder || mediaRecorder.state === "inactive") {
      isRecording.value = false;
      return null;
    }

    return new Promise((resolve) => {
      // Intercept the onstop event loop asynchronously
      mediaRecorder.onstop = async () => {
        const uploadResult = await handleFinishAndUpload(currentTitle, currentFolder);
        resolve(uploadResult); // Returns { name, route, share_url } back to Record.vue
      };

      mediaRecorder.stop();
      isRecording.value = false;
    });
  }

  async function handleFinishAndUpload(title, folder) {
    isUploading.value = true;
    const durationSeconds = Math.round((Date.now() - startedAt) / 1000);

    try {
      const res = await createRecordingDoc.submit({ title, folder });
      const recordingName = res.name || res;

      const blob = new Blob(chunks, { type: "video/webm" });
      const formData = new FormData();
      formData.append("file", new File([blob], `${recordingName}.webm`, { type: "video/webm" }));
      formData.append("doctype", "Screen Recording");
      formData.append("docname", recordingName);
      formData.append("fieldname", "video_file");
      formData.append("is_private", 0);

      const uploadRes = await fetch("/api/method/upload_file", {
        method: "POST",
        headers: { "X-Frappe-CSRF-Token": window.csrf_token },
        body: formData,
      }).then((r) => r.json());

      if (!uploadRes.message || !uploadRes.message.file_url) {
        throw new Error("File attachment failed.");
      }

      const finalResult = await finalizeRecordingDoc.submit({
        recording_name: recordingName,
        file_url: uploadRes.message.file_url,
        duration_seconds: durationSeconds,
      });

      isUploading.value = false;
      return finalResult;
    } catch (error) {
      console.error("Upload workflow interrupted:", error);
      isUploading.value = false;
      return null;
    }
  }

  return { isRecording, isUploading, start, stop };
}