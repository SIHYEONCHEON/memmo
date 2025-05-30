package com.example.thenewchatapp

import android.animation.ValueAnimator
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.EditText
import android.widget.ImageButton
import android.widget.PopupMenu
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.graphics.ColorUtils
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatDelegate
import com.example.thenewchatapp.MainActivity.Companion.prefs
import java.util.concurrent.TimeUnit

class FieldChatActivity : AppCompatActivity() {

    private lateinit var chatRecyclerView: RecyclerView
    private lateinit var messageEditText: EditText
    private lateinit var sendButton: ImageButton
    private lateinit var goToEditButton: ImageButton
    private lateinit var createResultButton: ImageButton
    private lateinit var btnPlus: ImageButton
    private lateinit var btnVoice: ImageButton
    private lateinit var btnDropdown: ImageButton
    private lateinit var recyclerCategory: RecyclerView
    private lateinit var recyclerEntry: RecyclerView
    private val viewModel: FieldViewModel by viewModels()
    private lateinit var tvFieldTitle: TextView

    private val chatMessages = mutableListOf<ChatMessage>()
    private lateinit var chatAdapter: ChatAdapter

    private lateinit var categoryAdapter: EasyCommandCategoryAdapter
    private lateinit var entryAdapter: EasyCommandEntryAdapter

    private val easyCommandMap = mutableMapOf(
        "요약" to mutableListOf("간단 요약: 이 내용을 간단하게 요약해줘"),
        "다듬기" to mutableListOf("문장 정리: 더 자연스럽게 바꿔줘"),
        "늘리기" to mutableListOf("내용 확장: 더 길게 써줘")
    )

    private var currentCategory: String = easyCommandMap.keys.first()

    private val fields = listOf(
        Field("목적", ""), Field("주제", ""), Field("독자", ""), Field("형식 혹은 구조", ""),
        Field("근거자료", ""), Field("어조", ""), Field("분량, 문체, 금지어 등", ""), Field("추가사항", "")
    )

    private val fieldKeys = listOf(
        "목적","주제","독자","형식 혹은 구조",
        "근거자료","어조","분량, 문체, 금지어 등","추가사항"
    )

    private val editMessageLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val editedText = result.data?.getStringExtra("editedText")
            val position = result.data?.getIntExtra("messagePosition", -1) ?: -1
            if (position in chatMessages.indices && editedText != null) {
                chatMessages[position] = chatMessages[position].copy(message = editedText)
                chatAdapter.notifyItemChanged(position)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        prefs = getSharedPreferences("settings", MODE_PRIVATE)
        AppCompatDelegate.setDefaultNightMode(
            prefs.getInt("theme_mode", AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM)
        )

        super.onCreate(savedInstanceState)
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        setContentView(R.layout.activity_chat_field)

        // 시스템 바/IME 패딩 처리
        val mainView = findViewById<View>(R.id.mainLayout)
        ViewCompat.setOnApplyWindowInsetsListener(mainView) { v, insets ->
            val sys = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            v.setPadding(sys.left, sys.top, sys.right, sys.bottom + ime.bottom)
            insets
        }

        // 뷰 바인딩
        chatRecyclerView = findViewById(R.id.chat_recyclerView)
        messageEditText = findViewById(R.id.editTextInput)
        sendButton = findViewById(R.id.btnSend)
        goToEditButton = findViewById(R.id.goToEditButton)
        createResultButton = findViewById(R.id.CreateResultButton)
        btnPlus         = findViewById(R.id.btnPlus)
        btnDropdown     = findViewById(R.id.btnFieldDropdown)
        recyclerCategory= findViewById(R.id.recyclerEasyCommand)
        recyclerEntry   = findViewById(R.id.recyclerCommandEntry)
        btnVoice = findViewById(R.id.btnVoice)
        tvFieldTitle      = findViewById(R.id.tvFieldTitle)

        // ViewModel 기본 제목 초기화 (한 번만)
        viewModel.initTitles(fieldKeys)

        // ② 드롭다운 메뉴: ViewModel 동기화 제목 사용
        btnDropdown.setOnClickListener { anchor ->
            PopupMenu(this, anchor).apply {
                fieldKeys.forEach { key ->
                    menu.add(viewModel.getTitle(key))
                }
                setOnMenuItemClickListener { item ->
                    val selectedLabel = item.title.toString()
                    // ③ 메뉴에서 고른 레이블(제목) 바로 반영
                    tvFieldTitle.text = selectedLabel
                    val key = fieldKeys.first { viewModel.getTitle(it) == selectedLabel }



                    // ③ 현재 입력 내용 저장
                    viewModel.setContent(key, messageEditText.text.toString())

                    // 🔥 서버에게 필드방 입장 알림
                    enterFieldRoom(key)

                    // ④ 선택된 필드로 재진입
                    val frag = FieldDetailFragment.newInstance(key, viewModel.getContent(key))
                    supportFragmentManager.beginTransaction()
                        .replace(R.id.fragmentContainer, frag)
                        .addToBackStack(null)
                        .commit()
                    true
                }
                show()
            }
        }

        btnVoice.setOnClickListener {
            Toast.makeText(this, "음성 인식이 시작됩니다.", Toast.LENGTH_SHORT).show()
        }

        // **1) ViewModel에 기본 필드명 채우기**
        val fieldKeys = fields.map { it.title }
        viewModel.initTitles(fieldKeys)

        // EasyCommand 리스트 기본 숨김
        recyclerCategory.visibility = View.GONE
        recyclerEntry.visibility   = View.GONE

        // EditText에 포커스 생길 때만 EasyCommand 보이기
        messageEditText.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) {
                recyclerCategory.visibility = View.VISIBLE
                recyclerEntry.visibility   = View.VISIBLE
            } else {
                recyclerCategory.visibility = View.GONE
                recyclerEntry.visibility   = View.GONE
            }
        }

        // 상단 EasyCommand 카테고리
        recyclerCategory.layoutManager =
            LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false)
        categoryAdapter = EasyCommandCategoryAdapter(
            easyCommandMap.keys.toList(),
            onCategoryClick = { selected ->
                currentCategory = selected
                updateEntryList()
            },
            onDeleteConfirmed = { category ->
                easyCommandMap.remove(category)
                refreshCategoryAdapter()
            }
        ).apply {
            setOnAddCategoryClickListener { showAddCategoryDialog() }
        }
        recyclerCategory.adapter = categoryAdapter

        // 하단 EasyCommand 엔트리
        recyclerEntry.layoutManager = LinearLayoutManager(this)
        entryAdapter = EasyCommandEntryAdapter(
            entries = emptyList(),
            onEditClick = { title, prompt -> openDetail(title, prompt) },
            onDeleteClick = { title ->
                easyCommandMap[currentCategory]?.removeIf { it.startsWith(title) }
                updateEntryList()
            },
            onPromptClick = { prompt -> messageEditText.setText(prompt) },
            onAddClick = { openDetail(null, null) }
        )
        recyclerEntry.adapter = entryAdapter

        // ➕ 버튼 팝업 메뉴
        btnPlus.setOnClickListener { anchorView ->
            // ▲ Gravity.TOP 지정: 메뉴를 버튼 위로 띄움
            val popup = PopupMenu(this, anchorView, Gravity.TOP)
            popup.apply {
                menu.add("필드 화면").setOnMenuItemClickListener {
                    intent = Intent(this@FieldChatActivity, FieldChatActivity::class.java)
                    startActivity(Intent(this@FieldChatActivity, FieldActivity::class.java))
                    true
                }
                show()
            }
        }

        // 초기 엔트리 리스트 세팅
        updateEntryList()

        // ① Intent extras 에서 key를 꺼내고, 없으면 첫 번째 필드 키 사용
        val keyFromIntent = intent.getStringExtra("field_title")
        val initialKey = if (keyFromIntent != null && fieldKeys.contains(keyFromIntent))
            keyFromIntent
        else
            fieldKeys.first()
        // ② ViewModel 에서 “보여줄 제목”(label)을 가져와 표시
        tvFieldTitle.text = viewModel.getTitle(initialKey)

        // **5+7. CommandDetailFragment에서 온 저장 결과 받기**
        supportFragmentManager.setFragmentResultListener(
            "easy_command_save", this
        ) { key, bundle ->
            val original = bundle.getString("original") ?: ""
            val title = bundle.getString("title") ?: return@setFragmentResultListener
            val prompt = bundle.getString("prompt") ?: return@setFragmentResultListener
            easyCommandMap[currentCategory]?.let { commands ->       // 바깥 it → commands 로 변경
                if (original.isNotBlank()) {
                    commands.removeIf { entry ->                      // 중첩 람다의 it → entry 로 변경
                        entry.startsWith("$original:")                // 문자열 템플릿 사용
                    }
                }
                // 새로 추가
                commands.add("$title:$prompt")
            }

            updateEntryList()
        }

        // 2) 루트 레이아웃 터치 시 포커스 해제
        mainView.setOnTouchListener { v: View, event: MotionEvent ->
            if (event.action == MotionEvent.ACTION_UP) {
                v.performClick()              // ← 클릭 처리(접근성용)
            }
            messageEditText.clearFocus()
            false
        }

        // **1. 포커스 해제 시 숨김 (이미 구현)**
        messageEditText.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) {
                recyclerCategory.visibility = View.VISIBLE
                recyclerEntry.visibility = View.VISIBLE
            } else {
                recyclerCategory.visibility = View.GONE
                recyclerEntry.visibility = View.GONE
            }
        }

        fun onBackPressed() {
            if (messageEditText.hasFocus()) {
                // EditText에 포커스 남아 있으면 해제만
                messageEditText.clearFocus()
            } else {
                // 그렇지 않으면 기본 뒤로가기
                super.onBackPressed()
            }
        }

        // 결과 생성 버튼 클릭
        createResultButton.setOnClickListener {
            // 1) 결과 전용 로딩 메시지 추가
            val loading = ChatMessage("결과 생성 중 입니다...", MessageType.LOADING_RESULT)
            chatMessages.add(loading)
            chatAdapter.notifyItemInserted(chatMessages.lastIndex)
            chatRecyclerView.smoothScrollToPosition(chatMessages.lastIndex)

            // 2) 실제 API 호출
            CoroutineScope(Dispatchers.Main).launch {
                // TODO: 실제 AI 호출 로직으로 교체
                delay(1500)
                // 로딩 제거
                val idx = chatMessages.indexOf(loading)
                if (idx >= 0) {
                    chatMessages.removeAt(idx)
                    chatAdapter.notifyItemRemoved(idx)
                }
                // 결과 메시지 추가
                val result = ChatMessage("결과 생성된 글입니다.", MessageType.RECEIVED, isResult = true)
                chatMessages.add(result)
                chatAdapter.notifyItemInserted(chatMessages.lastIndex)
                chatRecyclerView.smoothScrollToPosition(chatMessages.lastIndex)
            }
        }

        // MainActivity로 편집 이동
        goToEditButton.setOnClickListener {
            val intent = Intent(this, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            }
            startActivity(intent)
        }

        // RecyclerView 설정
        chatRecyclerView.layoutManager = LinearLayoutManager(this).apply { stackFromEnd = true }
        chatAdapter = ChatAdapter(chatMessages) { pos, text ->
            val intent = Intent(this, MainActivity::class.java).apply {
                putExtra("originalText", text)
                putExtra("messagePosition", pos)
            }
            editMessageLauncher.launch(intent)
        }
        chatRecyclerView.adapter = chatAdapter

        // 초기 대화 처리
        intent.getStringExtra("conversation")?.takeIf { it.isNotEmpty() }?.let {
            chatMessages += ChatMessage(it, MessageType.SENT)
            chatAdapter.notifyItemInserted(chatMessages.lastIndex)
            chatRecyclerView.smoothScrollToPosition(chatMessages.lastIndex)
            val reply = externalReply(it)
            chatMessages += ChatMessage(reply, MessageType.RECEIVED)
            chatAdapter.notifyItemInserted(chatMessages.lastIndex)
            chatRecyclerView.smoothScrollToPosition(chatMessages.lastIndex)
        }

        // 전송 버튼 클릭
        sendButton.setOnClickListener {
            val text = messageEditText.text.toString().trim()
            if (text.isNotEmpty()) {
                // 사용자 메시지 추가
                chatMessages += ChatMessage(text, MessageType.SENT)
                chatAdapter.notifyItemInserted(chatMessages.lastIndex)
                chatRecyclerView.smoothScrollToPosition(chatMessages.lastIndex)
                messageEditText.text.clear()

                // 일반 로딩 메시지 추가
                val loading = ChatMessage("답변 생성 중 입니다...", MessageType.LOADING)
                chatMessages += loading
                chatAdapter.notifyItemInserted(chatMessages.lastIndex)
                chatRecyclerView.smoothScrollToPosition(chatMessages.lastIndex)

                // AI 응답 스트리밍
                CoroutineScope(Dispatchers.Main).launch {
                    val response = ChatMessage("", MessageType.RECEIVED)
                    chatAdapter.sendChatRequest(text) { chunk ->
                        if (loading in chatMessages) {
                            val idx = chatMessages.indexOf(loading)
                            chatMessages.removeAt(idx)
                            chatAdapter.notifyItemRemoved(idx)
                        }
                        if (response !in chatMessages) {
                            chatMessages += response
                            chatAdapter.notifyItemInserted(chatMessages.lastIndex)
                        }
                        response.message += chunk
                        chatAdapter.notifyItemChanged(chatMessages.indexOf(response))
                        chatRecyclerView.smoothScrollToPosition(chatMessages.lastIndex)
                    }
                }
            }
        }
    }

    private fun externalReply(sentMsg: String): String = "Reply to: $sentMsg"

    class ChatAdapter(
        private val messages: List<ChatMessage>,
        private val onReceivedClick: (Int, String) -> Unit
    ) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

        companion object {
            private const val VIEW_TYPE_SENT = 1
            private const val VIEW_TYPE_RECEIVED = 2
            private const val VIEW_TYPE_RESULT = 3
            private const val VIEW_TYPE_LOADING = 4
            private const val VIEW_TYPE_LOADING_RESULT = 5
        }

        override fun getItemViewType(position: Int): Int = with(messages[position]) {
            when {
                type == MessageType.SENT               -> VIEW_TYPE_SENT
                type == MessageType.LOADING_RESULT     -> VIEW_TYPE_LOADING_RESULT
                type == MessageType.LOADING            -> VIEW_TYPE_LOADING
                type == MessageType.RECEIVED && isResult -> VIEW_TYPE_RESULT
                else                                   -> VIEW_TYPE_RECEIVED
            }
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder =
            LayoutInflater.from(parent.context).run {
                when (viewType) {
                    VIEW_TYPE_SENT           -> SentViewHolder(inflate(R.layout.sent_message_bubble, parent, false))
                    VIEW_TYPE_LOADING_RESULT -> ResultLoadingViewHolder(inflate(R.layout.result_loading_message_bubble, parent, false))
                    VIEW_TYPE_LOADING        -> LoadingViewHolder(inflate(R.layout.loading_message_bubble, parent, false))
                    VIEW_TYPE_RESULT         -> ResultViewHolder(inflate(R.layout.result_received_message_bubble, parent, false))
                    else                     -> ReceivedViewHolder(inflate(R.layout.received_message_bubble, parent, false))
                }
            }

        override fun getItemCount(): Int = messages.size

        override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
            val msg = messages[position]
            when (holder) {
                is SentViewHolder           -> holder.bind(msg)
                is ReceivedViewHolder       -> holder.bind(msg)
                is ResultViewHolder         -> holder.bind(msg, onReceivedClick)
                is LoadingViewHolder        -> holder.bind()
                is ResultLoadingViewHolder  -> holder.bind()
            }
        }

        class SentViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            private val tv: TextView = view.findViewById(R.id.sent_message_bubble)
            fun bind(msg: ChatMessage) { tv.text = msg.message }
        }

        class ReceivedViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            private val tv: TextView = view.findViewById(R.id.receive_message_bubble)
            fun bind(msg: ChatMessage) { tv.apply { text = msg.message; setOnClickListener(null) } }
        }

        class ResultViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            private val tv: TextView = view.findViewById(R.id.result_receive_message_bubble)
            fun bind(msg: ChatMessage, click: (Int, String) -> Unit) {
                tv.text = msg.message
                tv.setOnClickListener { click(adapterPosition, msg.message) }
            }
        }

        class LoadingViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            private val tv: TextView = view.findViewById(R.id.loading_text)
            private var animator: ValueAnimator? = null
            fun bind() {
                val base = tv.currentTextColor
                animator?.cancel()
                animator = ValueAnimator.ofFloat(0.3f, 1f).apply {
                    duration = 1000
                    repeatMode = ValueAnimator.REVERSE
                    repeatCount = ValueAnimator.INFINITE
                    addUpdateListener {
                        val a = (it.animatedValue as Float * 255).toInt()
                        tv.setTextColor(ColorUtils.setAlphaComponent(base, a))
                    }
                    start()
                }
                tv.text = "답변 생성 중 입니다..."
            }
        }

        class ResultLoadingViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            private val tv: TextView = view.findViewById(R.id.result_loading_text)
            private var animator: ValueAnimator? = null
            fun bind() {
                val base = tv.currentTextColor
                animator?.cancel()
                animator = ValueAnimator.ofFloat(0.3f, 1f).apply {
                    duration = 1000
                    repeatMode = ValueAnimator.REVERSE
                    repeatCount = ValueAnimator.INFINITE
                    addUpdateListener {
                        val a = (it.animatedValue as Float * 255).toInt()
                        tv.setTextColor(ColorUtils.setAlphaComponent(base, a))
                    }
                    start()
                }
                tv.text = "결과 생성 중 입니다..."
            }
        }

        fun sendChatRequest(userMessage: String, onChunk: (String) -> Unit) {
            CoroutineScope(Dispatchers.IO).launch {
                val client = OkHttpClient.Builder() //소켓타임아웃방지코드
                    .connectTimeout(30, TimeUnit.SECONDS)  // 연결 타임아웃 30초
                    .readTimeout(0, TimeUnit.SECONDS)      // 스트리밍 응답 무제한 대기 (중요!)
                    .writeTimeout(30, TimeUnit.SECONDS)    // 쓰기 타임아웃 30초
                    .build()
                val body = JSONObject().put("message", userMessage).toString()
                    .toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
                val req = Request.Builder()
                    .url("http://54.252.159.52:5000/stream-chat")
                    .post(body)
                    .build()
                try {
                    client.newCall(req).execute().use { resp ->
                        if (!resp.isSuccessful) return@use onChunk("Error: ${resp.code}")
                        val src = resp.body?.source() ?: return@use onChunk("Error: null body")
                        while (src.request(1)) {
                            val chunk = src.buffer.readUtf8(minOf(1024L, src.buffer.size))
                            withContext(Dispatchers.Main) { onChunk(chunk) }
                        }
                    }
                } catch (e: Exception) {
                    withContext(Dispatchers.Main) { onChunk("Stream Error: ${e.message}") }
                }
            }
        }
    }

    private fun updateEntryList() {
        val list = easyCommandMap[currentCategory]?.map {
            val parts = it.split(":")
            parts[0] to parts.getOrNull(1).orEmpty()
        }?.toMutableList() ?: mutableListOf()
        list.add("+" to "")
        entryAdapter.updateList(list)
    }

    private fun refreshCategoryAdapter() {
        categoryAdapter = EasyCommandCategoryAdapter(
            easyCommandMap.keys.toList(),
            categoryAdapter.onCategoryClick,
            categoryAdapter.onDeleteConfirmed
        ).apply { setOnAddCategoryClickListener { showAddCategoryDialog() } }
        recyclerCategory.adapter = categoryAdapter
        updateEntryList()
    }

    private fun showAddCategoryDialog() {
        val input = EditText(this)
        AlertDialog.Builder(this)
            .setTitle("카테고리 추가")
            .setView(input)
            .setPositiveButton("추가") { _, _ ->
                val name = input.text.toString().trim()
                if (name.isNotBlank() && !easyCommandMap.containsKey(name)) {
                    easyCommandMap[name] = mutableListOf()
                    refreshCategoryAdapter()
                }
            }
            .setNegativeButton("취소", null)
            .show()
    }

    private fun openDetail(title: String?, prompt: String?) {
        CommandDetailFragment.newInstance(currentCategory, title, prompt)
            .show(supportFragmentManager, "CommandDetail")
    }


    // ✅ 이 위치에 함수 추가!
    private fun enterFieldRoom(fieldKey: String) {
        CoroutineScope(Dispatchers.IO).launch {
            val client = OkHttpClient()
            val url = "http://http://54.252.159.52:5000/enter-sub-conversation/$fieldKey"
            val req = Request.Builder().url(url)
                .post("".toRequestBody("application/json".toMediaTypeOrNull()))
                .build()

            try {
                client.newCall(req).execute().use { resp ->
                    if (!resp.isSuccessful) {
                        println("서버 입장 실패: ${resp.code}")
                    } else {
                        println("서버 입장 성공: ${resp.body?.string()}")
                    }
                }
            } catch (e: Exception) {
                println("서버 입장 요청 에러: ${e.message}")
            }
        }
    }

    companion object {
        fun newInstance(): FieldChatActivity = FieldChatActivity()
    }
}


