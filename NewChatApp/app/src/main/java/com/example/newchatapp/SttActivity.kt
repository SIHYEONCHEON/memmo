package com.example.newchatapp

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.EditText
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.app.ActivityCompat
import com.google.api.gax.core.FixedCredentialsProvider
import com.google.auth.oauth2.GoogleCredentials
import com.google.cloud.speech.v1.*
import com.google.protobuf.ByteString
import kotlinx.coroutines.*
import android.speech.SpeechRecognizer
import android.content.Context
import android.content.Intent
import com.google.api.gax.rpc.ApiStreamObserver

class SttActivity : ComponentActivity() {

    private lateinit var transcriptEditText: EditText
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var confirmButton: Button

    private var recording = false
    private var audioRecord: AudioRecord? = null
    private var speechClient: SpeechClient? = null
    private var speechRecognizer: SpeechRecognizer? = null

    private val sampleRate = 48000
    private var packetCount = 0
    private var lastTranscript: String = "" // ✅ 마지막 인식된 텍스트 저장 변수
    private val bufferSize = AudioRecord.getMinBufferSize(
        sampleRate,
        AudioFormat.CHANNEL_IN_MONO,
        AudioFormat.ENCODING_PCM_16BIT
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_chat)

        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this)

        transcriptEditText = findViewById(R.id.message_edit)
        startButton = findViewById(R.id.start_button)
        stopButton = findViewById(R.id.stop_button)
        confirmButton = findViewById(R.id.confirm_button)

        requestAudioPermission()
        initializeGoogleCredentials()
        checkPermissions()

        stopButton.isEnabled = false

        SpeechRecognitionHelper.onStartRecognition = {
            startSpeechToText()
        }

        SpeechRecognitionHelper.onStopRecognition = {
            stopSpeechToText()
        }

        startButton.setOnClickListener {
            if (!recording) {
                val startIntent = Intent(this, STTService::class.java).apply {
                    putExtra("ACTION", "START")
                }
                startService(startIntent)

                startButton.isEnabled = false
                stopButton.isEnabled = true
            }
        }

        stopButton.setOnClickListener {
            pauseSpeechToText()

            val stopIntent = Intent(this, STTService::class.java).apply {
                putExtra("ACTION", "STOP")
            }
            startService(stopIntent)
        }

        confirmButton.setOnClickListener {
            val finalText = processFinalText(transcriptEditText.text.toString())
            transcriptEditText.setText(finalText)
            transcriptEditText.setSelection(transcriptEditText.text.length)

            finalizeSpeechRecognition()

            val confirmIntent = Intent(this, STTService::class.java).apply {
                putExtra("ACTION", "CONFIRM")
            }
            startService(confirmIntent)
        }
    }

    private fun finalizeSpeechRecognition() {
        val intent = Intent(this, STTService::class.java).apply {
            putExtra("ACTION", "CONFIRM")
        }
        startService(intent)
    }

    private fun checkPermissions() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), 1001)
        }
    }

    private fun requestAudioPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            Log.d("STT", "Microphone permission granted")
        } else {
            Log.e("STT_ERROR", "Microphone permission denied")
        }
    }

    private fun initializeGoogleCredentials() {
        try {
            applicationContext.assets.open("service-account-key.json").use { inputStream ->
                val credentials = GoogleCredentials.fromStream(inputStream)
                    .createScoped(listOf("https://www.googleapis.com/auth/cloud-platform"))

                val speechSettings = SpeechSettings.newBuilder()
                    .setCredentialsProvider(FixedCredentialsProvider.create(credentials))
                    .build()

                speechClient = SpeechClient.create(speechSettings)
                Log.d("STT", "✅ Google Cloud Credentials loaded successfully!")
            }
        } catch (e: Exception) {
            Log.e("STT_ERROR", "❌ Failed to set up credentials", e)
            speechClient = null
        }

        if (speechClient == null) {
            Log.e("STT_ERROR", "❌ SpeechClient 초기화 실패 - credentials 설정 오류 가능성 있음")
        } else {
            Log.d("STT", "✅ SpeechClient가 정상적으로 초기화됨")
        }
    }

    private fun startSpeechToText() {
        if (!isMicrophoneAvailable()) {
            Log.e("STT_ERROR", "마이크를 사용할 수 없음")
            return
        }

        if (speechClient == null) {
            Log.e("STT_ERROR", "❌ SpeechClient가 초기화되지 않음")
            return
        }

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e("STT_ERROR", "❌ AudioRecord 초기화 실패")
                return
            }

            audioRecord?.startRecording()
            recording = true

            runOnUiThread {
                startButton.isEnabled = false
                stopButton.isEnabled = true
            }

            Log.d("STT", "🎤 음성 인식 시작됨")

            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val responseObserver = object : ApiStreamObserver<StreamingRecognizeResponse> {
                        override fun onNext(response: StreamingRecognizeResponse?) {
                            Log.d("STT_DEBUG", "🎤 onNext() 호출됨")
                            response?.resultsList?.forEach { result ->
                                val transcript = result.alternativesList.joinToString { it.transcript }
                                Log.d("STT", "✅ 인식된 텍스트(원본): $transcript")

                                runOnUiThread {
                                    val processedText = processFinalText(transcript)  // ✅ 텍스트 정리 적용
                                    if (processedText != lastTranscript) {
                                        lastTranscript = processedText
                                        transcriptEditText.append(" $processedText")
                                        transcriptEditText.setSelection(transcriptEditText.text.length)
                                    } else {
                                        Log.d("STT", "🔄 동일한 텍스트 감지됨, 추가 안 함")
                                    }
                                }
                            }
                        }

                        override fun onError(t: Throwable?) {
                            Log.e("STT_ERROR", "❌ STT 오류 발생: ${t?.message}")
                        }

                        override fun onCompleted() {
                            Log.d("STT", "✅ STT 완료")
                        }
                    }

                    val requestObserver = speechClient!!
                        .streamingRecognizeCallable()
                        .bidiStreamingCall(responseObserver)

                    val streamingConfig = StreamingRecognitionConfig.newBuilder()
                        .setConfig(
                            RecognitionConfig.newBuilder()
                                .setEncoding(RecognitionConfig.AudioEncoding.LINEAR16)
                                .setSampleRateHertz(sampleRate)
                                .setLanguageCode("ko-KR")
                                .setModel("default")
                                .build()
                        )
                        .setInterimResults(false)
                        .build()

                    requestObserver.onNext(
                        StreamingRecognizeRequest.newBuilder()
                            .setStreamingConfig(streamingConfig)
                            .build()
                    )

                    val buffer = ByteArray(bufferSize)
                    while (recording) {
                        val bytesRead = audioRecord?.read(buffer, 0, buffer.size) ?: 0

                        if (bytesRead > 0) {
                            packetCount++
                            if (packetCount % 10 == 0) {  // 10번째 패킷마다 로그 출력
                                Log.d("STT", "📢 음성 데이터 전송 중: $bytesRead bytes")
                            }
                        } else {
                            Log.e("STT_ERROR", "❌ 음성 데이터 없음 (bytesRead = $bytesRead)")
                        }

                        requestObserver.onNext(
                            StreamingRecognizeRequest.newBuilder()
                                .setAudioContent(ByteString.copyFrom(buffer, 0, bytesRead))
                                .build()
                        )
                    }
                    requestObserver.onCompleted()
                } catch (e: Exception) {
                    Log.e("STT_ERROR", "❌ 음성 인식 중 오류 발생", e)
                }
            }
        } catch (e: Exception) {
            Log.e("STT_ERROR", "❌ STT 실행 중 오류 발생", e)
        }
    }

    private fun isMicrophoneAvailable(): Boolean {
        val audioManager = getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
        return packageManager.hasSystemFeature(PackageManager.FEATURE_MICROPHONE) &&
                audioManager.mode != android.media.AudioManager.MODE_INVALID
    }

    private fun stopSpeechToText() {
        recording = false
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null

        runOnUiThread {
            startButton.isEnabled = true
            stopButton.isEnabled = false
        }

        speechClient?.shutdown()  // 최종 종료
        speechClient = null
        Log.d("STT", "🛑 음성 인식 완전 종료됨")
    }

    private fun pauseSpeechToText() {
        if (recording) {
            recording = false  // 녹음 중단
            audioRecord?.stop()  // 오디오 입력을 일시 정지
            runOnUiThread {
                startButton.isEnabled = true  // 시작 버튼 활성화
                stopButton.isEnabled = false  // 중지 버튼 비활성화
            }
            Log.d("STT", "⏸ 음성 인식 일시 정지됨")
        }
    }

    fun processFinalText(input: String): String {
        val cleaned = cleanUpText(input)  // 불필요한 반복 문자 제거
        return finalizeSentence(cleaned)  // 문장 끝에 적절한 구두점 추가
    }

    private fun cleanUpText(input: String): String {
        val cleanedText = input.replace(Regex("(.)\\1{2,}"), "$1")  // 중복 문자 제거
        return cleanedText.replace(Regex("\\s+"), " ").trim()  // 공백 정리
    }

    private fun finalizeSentence(input: String): String {
        val trimmedText = input.trim()

        // 문장이 비어있다면 그대로 반환
        if (trimmedText.isEmpty()) return trimmedText

        // ✅ 질문이면 물음표 추가
        if (trimmedText.endsWith("뭐야") || trimmedText.endsWith("어떻게") || trimmedText.endsWith("왜") ||
            trimmedText.endsWith("인지") || trimmedText.endsWith("인가") || trimmedText.endsWith("까")) {
            return if (trimmedText.endsWith("?")) trimmedText else "$trimmedText?"
        }

        // ✅ 기존 코드에서 마침표 추가하는 부분을 삭제 (중요!)
        return trimmedText  // 마침표 추가 없이 그대로 반환
    }
}
