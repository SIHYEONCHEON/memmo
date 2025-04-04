package com.example.newchatapp

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import android.speech.SpeechRecognizer
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.TextView
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.api.gax.core.FixedCredentialsProvider
import com.google.api.gax.rpc.ApiStreamObserver
import com.google.auth.oauth2.GoogleCredentials
import com.google.cloud.speech.v1.RecognitionConfig
import com.google.cloud.speech.v1.SpeechClient
import com.google.cloud.speech.v1.SpeechSettings
import com.google.cloud.speech.v1.StreamingRecognitionConfig
import com.google.cloud.speech.v1.StreamingRecognizeRequest
import com.google.cloud.speech.v1.StreamingRecognizeResponse
import com.google.protobuf.ByteString
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

// -------------------------
// 데이터 클래스 & 열거형
// -------------------------
data class ChatMessage(
    var message: String,         // 스트리밍 중 실시간 갱신을 위해 var
    val type: MessageType
)

enum class MessageType {
    SENT,
    RECEIVED
}

// -------------------------
// RecyclerView 어댑터
// -------------------------
class ChatAdapter(private val messages: List<ChatMessage>) :
    RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    companion object {
        private const val VIEW_TYPE_SENT = 1
        private const val VIEW_TYPE_RECEIVED = 2
    }

    override fun getItemViewType(position: Int): Int {
        return when (messages[position].type) {
            MessageType.SENT -> VIEW_TYPE_SENT
            MessageType.RECEIVED -> VIEW_TYPE_RECEIVED
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        return if (viewType == VIEW_TYPE_SENT) {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.sent_message_bubble, parent, false)
            SentMessageViewHolder(view)
        } else {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.received_message_bubble, parent, false)
            ReceivedMessageViewHolder(view)
        }
    }

    override fun getItemCount(): Int = messages.size

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        val chatMessage = messages[position]
        when (holder) {
            is SentMessageViewHolder -> holder.bind(chatMessage)
            is ReceivedMessageViewHolder -> holder.bind(chatMessage)
        }
    }

    // 내가 보낸 메시지 (오른쪽 말풍선)
    class SentMessageViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val sentMessageText: TextView = itemView.findViewById(R.id.sent_message_bubble)
        fun bind(chatMessage: ChatMessage) {
            sentMessageText.text = chatMessage.message
        }
    }

    // GPT/상대방 메시지 (왼쪽 말풍선)
    class ReceivedMessageViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val receivedMessageText: TextView =
            itemView.findViewById(R.id.receive_message_bubble)
        fun bind(chatMessage: ChatMessage) {
            receivedMessageText.text = chatMessage.message
        }
    }
}

// -------------------------
// 액티비티
// -------------------------
class ChatActivity : AppCompatActivity() {

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

    private lateinit var chatRecyclerView: RecyclerView
    private lateinit var messageEditText: EditText
    private lateinit var sendButton: ImageButton

    // 채팅 메시지 리스트
    private val chatMessages = mutableListOf<ChatMessage>()

    // RecyclerView 어댑터
    private lateinit var chatAdapter: ChatAdapter
    private var currentResponseMessage: ChatMessage? = null
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE) // 입력필드 키보드 위로 1
        setContentView(R.layout.activity_chat)


        // 입력필드 키보드 위로 2
        val mainView = findViewById<View>(R.id.main)
        ViewCompat.setOnApplyWindowInsetsListener(mainView) { v, insets ->
            val systemBarsInsets = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val imeInsets = insets.getInsets(WindowInsetsCompat.Type.ime())
            v.setPadding(
                systemBarsInsets.left,
                systemBarsInsets.top,
                systemBarsInsets.right,
                systemBarsInsets.bottom + imeInsets.bottom
            )
            insets
        }

        // 뷰 참조
        chatRecyclerView = findViewById(R.id.chat_recyclerView)
        messageEditText = findViewById(R.id.message_edit)
        sendButton = findViewById(R.id.send_btn)

        // RecyclerView 설정
        chatAdapter = ChatAdapter(chatMessages)
        chatRecyclerView.adapter = chatAdapter
        chatRecyclerView.layoutManager = LinearLayoutManager(this)

        // 메시지 전송 버튼 클릭 리스너
        sendButton.setOnClickListener {
            // 1. 사용자가 입력한 메시지를 sentMessage 변수에 저장
            val sentMessage: String = messageEditText.text.toString().trim()
            if (sentMessage.isNotEmpty()) {
                // 2. 보낸 메시지 객체를 생성하여 RecyclerView에 추가 (sent_message_bubble.xml 사용)
                val newSentMessage = ChatMessage(sentMessage, MessageType.SENT)
                chatMessages.add(newSentMessage)
                chatAdapter.notifyItemInserted(chatMessages.size - 1)
                chatRecyclerView.scrollToPosition(chatMessages.size - 1) // 마지막 메시지 보이도록 스크롤
                messageEditText.text.clear()
                // **3. 새로운 받은 메시지 UI 요소 생성 (초기 상태 - 비어 있거나 로딩 표시)**
                currentResponseMessage = ChatMessage("", MessageType.RECEIVED) // 빈 메시지 객체 생성
                currentResponseMessage?.let {
                    chatMessages.add(it)
                    chatAdapter.notifyItemInserted(chatMessages.size - 1)
                    chatRecyclerView.scrollToPosition(chatMessages.size - 1)
                }


                // 3. 서버에 채팅 요청 (sendChatRequest 함수 사용)
                lifecycleScope.launch { // lifecycleScope 사용
                    sendChatRequest(sentMessage) { chunk:String -> // 청크 단위 응답 처리
                        // 4. 받은 청크 데이터를 UI에 표시 (received_message_bubble.xml 사용)
                        currentResponseMessage?.let { message ->
                            val updatedMessage = message.message + chunk // 기존 메시지에 청크 추가
                            currentResponseMessage = message.copy(message = updatedMessage)

                            // UI 업데이트 (해당 아이템만 업데이트)
                            val messageIndex = chatMessages.indexOf(message)
                            if (messageIndex != -1) {
                                chatMessages[messageIndex] = currentResponseMessage!!
                                chatAdapter.notifyItemChanged(messageIndex)
                                chatRecyclerView.scrollToPosition(messageIndex)
                            }
                        }
                    }}}
        }
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

    /**
     * 서버(GPT)로부터 스트리밍 응답을 받아오는 함수
     * - 왼쪽 말풍선을 실시간으로 업데이트
     */


suspend fun sendChatRequest(userMessage: String, onChunk: (String) -> Unit) {
    withContext(Dispatchers.IO) {
        val client = OkHttpClient()
        val json = JSONObject().apply {
            put("message", userMessage)
        }
        val mediaType = "application/json; charset=utf-8".toMediaTypeOrNull()
        val requestBody = json.toString().toRequestBody(mediaType)
        val request = Request.Builder()
            .url("http://10.0.2.2:8000/stream-chat") // URL 확인 필요
            .post(requestBody)
            .build()

        try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    withContext(Dispatchers.Main) {
                        onChunk("Error: ${response.code}")
                    }
                    return@withContext
                }
                val source = response.body?.source() ?: run {
                    withContext(Dispatchers.Main) {
                        onChunk("Error: Response body is null")
                    }
                    return@withContext
                }
                val fixedBufferSize = 1024L

                while (true) {
                    if (!source.request(1L)) break

                    val available = source.buffer.size
                    if (available > 0) {
                        val bytesToRead = if (available >= fixedBufferSize) fixedBufferSize else available
                        val chunk = try {
                            source.readUtf8(bytesToRead)
                        } catch (readEx: Exception) {
                            withContext(Dispatchers.Main) {
                                onChunk("Stream Read Error: ${readEx.message}")
                            }
                            break
                        }
                        withContext(Dispatchers.Main) {
                            onChunk(chunk)
                        }
                    }
                }
            }
        } catch (e: Exception) {
            withContext(Dispatchers.Main) {
                onChunk("Stream Error: ${e.message}")
            }
        }
    }
}