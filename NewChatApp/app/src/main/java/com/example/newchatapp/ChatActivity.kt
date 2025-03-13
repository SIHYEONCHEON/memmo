package com.example.newchatapp

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.ImageButton
import android.widget.TextView
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
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
        enableEdgeToEdge()          // 엣지 투 엣지 모드
        setContentView(R.layout.activity_chat)

        // 시스템 바(상단·하단) 패딩 적용
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.main)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
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
}}