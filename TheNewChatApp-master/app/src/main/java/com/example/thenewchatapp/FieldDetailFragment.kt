package com.example.thenewchatapp

import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import android.view.*
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.PopupMenu
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class FieldDetailFragment : Fragment(R.layout.fragment_field_detail) {

    private lateinit var editTextTitle: EditText
    private lateinit var editTextContent: EditText
    private lateinit var btnVoice: ImageButton
    private lateinit var btnPlus: ImageButton
    private val viewModel: FieldViewModel by activityViewModels()
    private lateinit var fragmentContainer: FrameLayout

    // arguments 로 넘어온 필드 제목/내용
    private var titleArg: String = ""
    private var contentArg: String = ""

    companion object {
        private const val ARG_TITLE = "title"
        private const val ARG_CONTENT = "content"

        fun newInstance(title: String, content: String): FieldDetailFragment {
            return FieldDetailFragment().apply {
                arguments = Bundle().apply {
                    putString(ARG_TITLE, title)
                    putString(ARG_CONTENT, content)
                }
            }
        }
    }

    // 🆕 한글 필드 → 서버용 영문 키 매핑
    private val fieldNameToKey = mapOf(
        "목적" to "purpose_background",
        "주제" to "context_topic",
        "독자" to "audience_scope",
        "형식 혹은 구조" to "format_structure",
        "근거자료" to "logic_evidence",
        "어조" to "expression_method",
        "분량, 문체, 금지어 등" to "additional_constraints",
        "추가사항" to "output_expectations"
    )

    private val fieldKeys = listOf(
        "목적","주제","독자","형식 혹은 구조",
        "근거자료","어조","분량, 문체, 금지어 등","추가사항"
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        arguments?.let {
            titleArg   = it.getString(ARG_TITLE, "")
            contentArg = it.getString(ARG_CONTENT, "")
        }
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        editTextTitle   = view.findViewById(R.id.editTextTitle)
        editTextContent = view.findViewById(R.id.editTextContent)
        btnVoice        = view.findViewById(R.id.btnVoice)
        btnPlus         = view.findViewById(R.id.btnPlus)
        fragmentContainer = view.findViewById(R.id.fragmentContainer)

        // 제목/내용 초기화
        editTextTitle.setText(titleArg)
        editTextContent.setText(contentArg)

        // ViewModel에서 값 불러오기
        val initialTitle = viewModel.getTitle(titleArg).ifEmpty { titleArg }
        editTextTitle.setText(initialTitle)
        editTextContent.setText(viewModel.getContent(titleArg))

        // 변경 감지 리스너
        editTextTitle.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                viewModel.setTitle(titleArg, s.toString())
            }
            override fun beforeTextChanged(s: CharSequence?, st: Int, c: Int, a: Int) = Unit
            override fun onTextChanged(s: CharSequence?, st: Int, b: Int, c: Int) = Unit
        })

        editTextContent.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                viewModel.setContent(titleArg, s.toString())
            }
            override fun beforeTextChanged(s: CharSequence?, st: Int, c: Int, a: Int) = Unit
            override fun onTextChanged(s: CharSequence?, st: Int, b: Int, c: Int) = Unit
        })

        // + 버튼 팝업
        btnPlus.setOnClickListener { anchor ->
            PopupMenu(requireContext(), anchor).apply {
                // 통합 B의 Gravity.TOP 유지
                gravity = Gravity.TOP

                menu.add("챗봇").setOnMenuItemClickListener {
                    val intent = Intent(requireActivity(), FieldChatActivity::class.java)
                    startActivity(intent)
                    true
                }

                //  글 정리 기능 추가
                menu.add("글 정리").setOnMenuItemClickListener {
                    val fieldKey = fieldNameToKey[titleArg] ?: titleArg
                    updateFieldViaServer(fieldKey, editTextContent.text.toString(), titleArg)
                    true
                }
                show()
            }
        }

        // 음성 버튼
        btnVoice.setOnClickListener {
            Toast.makeText(requireContext(), "음성 인식 기능은 추후 추가됩니다.", Toast.LENGTH_SHORT).show()
        }

        // 포커스 리스너
        editTextTitle.setOnFocusChangeListener { _, has ->
            if (!has) savedFieldTitles[titleArg] = editTextTitle.text.toString()
        }
        editTextContent.setOnFocusChangeListener { _, has ->
            if (!has) savedFieldContents[titleArg] = editTextContent.text.toString()
        }
    }

    // 임시 저장용 맵
    private val savedFieldTitles   = mutableMapOf<String, String>()
    private val savedFieldContents = mutableMapOf<String, String>()

    //  서버 통신 함수
    private fun updateFieldViaServer(fieldKey: String, content: String, fieldLabel: String) {
        val client = OkHttpClient.Builder() //소켓타임아웃방지코드
            .connectTimeout(1, TimeUnit.DAYS)
            .readTimeout(1, TimeUnit.DAYS)
            .writeTimeout(1, TimeUnit.DAYS)
            .build()

        val json = JSONObject().apply {
            put("field_name", fieldKey)
            put("content", content)
        }

        val requestBody = json.toString().toRequestBody("application/json".toMediaType())
        Log.d("UpdateDebug", "Sending to server: field=$fieldKey, content=$content")
        val request = Request.Builder()
            .url("http://54.252.159.52:5000/update-field")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                activity?.runOnUiThread {
                    Toast.makeText(requireContext(), "서버 연결 실패", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onResponse(call: Call, response: Response) {
                val bodyString = response.body?.string()
                Log.d("UpdateDebug", "응답 코드: ${response.code}")
                Log.d("UpdateDebug", "응답 본문: $bodyString")

                if (!response.isSuccessful || bodyString == null) {
                    activity?.runOnUiThread {
                        Toast.makeText(requireContext(), "서버 응답 오류", Toast.LENGTH_SHORT).show()
                    }
                    return
                }

                try {
                    val json = JSONObject(bodyString)
                    val rawSummary = json.optString("content", "요약 실패")

                    val bodyOnly = Regex("<BODY>(.*?)</BODY>", RegexOption.DOT_MATCHES_ALL)
                        .find(rawSummary)
                        ?.groups?.get(1)
                        ?.value
                        ?.replace(Regex("-\\s*"), "")
                        ?.replace("\\s+".toRegex(), " ")
                        ?.trim()
                        ?: rawSummary

                    activity?.runOnUiThread {
                        editTextContent.setText(bodyOnly)
                        viewModel.setContent(fieldLabel, bodyOnly)
                        Toast.makeText(requireContext(), "요약 및 저장 완료", Toast.LENGTH_SHORT).show()
                    }
                } catch (e: Exception) {
                    Log.e("UpdateDebug", "응답 파싱 중 오류: ${e.localizedMessage}")
                    activity?.runOnUiThread {
                        Toast.makeText(requireContext(), "응답 파싱 실패", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        })
    }
}