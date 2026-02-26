using UnityEngine;
using UnityEngine.UI;
using System.IO.Ports;
using System.Collections;
using System.Collections.Concurrent;
using System.IO;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;

public class ReactionTestManager : MonoBehaviour
{
    // 実験の状態管理
    enum State { Idle, ReturnToCenter, WaitRandom, Measuring }

    // --- インスペクタ設定項目 ---

    [Header("Hardware Settings")]
    [Tooltip("Arduinoのポート名 (例: COM5, /dev/tty.usbmodem...)")]
    public string portName = "COM5";
    public int baudRate = 9600;

    [Header("EMS Config (Biphasic / Single Pulse)")]
    [Tooltip("EMS刺激を有効にする。OFFにすると視覚ターゲットのみで刺激は送信されません。")]
    public bool emsEnabled = true;

    [Range(20, 1000)]
    [Tooltip("パルス幅 (µs)。単一パルスの場合は50µs前後が鋭い刺激になります。")]
    public int emsPulseWidth = 50; // ★デフォルト: 50µs

    [Range(1, 100)]
    [Tooltip("刺激の連射回数。単一パルスなら「1」。バースト波なら「5〜50」。")]
    public int emsPulseCount = 1;  // ★デフォルト: 1回 (単発)

    [Range(1, 20)]
    [Tooltip("1回の繰り返しに含まれる2相性サイクル数。デフォルト3。")]
    public int emsBurstCount = 3;  // ★デフォルト: 3サイクル/繰り返し

    [Range(0, 100000)]
    [Tooltip("連射時のパルス間隔 (µs)。Count=1の場合は無視されます。")]
    public int emsPulseInterval = 40000; // 40ms (25Hz)

    [Header("Test Trigger (Calibration)")]
    [Tooltip("チェックを入れると左用の刺激をテスト発火します")]
    public bool testTriggerLeft = false;
    [Tooltip("チェックを入れると右用の刺激をテスト発火します")]
    public bool testTriggerRight = false;

    [Header("Stimulation Timing")]
    [Tooltip("左(撓屈)ターゲット出現からの遅延時間(秒)。マイナス値で先行刺激。")]
    public float stimulusTimingOffsetLeft = 0.0f;
    [Tooltip("右(尺屈)ターゲット出現からの遅延時間(秒)。マイナス値で先行刺激。")]
    public float stimulusTimingOffsetRight = 0.0f;

    [Header("Game Objects")]
    public GameObject targetLeft;
    public GameObject targetRight;
    public GameObject targetCenter;
    public Transform playerBody;   // 回転するプレイヤー本体
    public Transform playerCamera; // Rayを飛ばすカメラ

    [Header("UI Settings")]
    public Image crosshairImage;
    public Color crosshairNormalColor = Color.white;
    public Color crosshairActiveColor = Color.red;

    [Header("UI (Reaction Time)")]
    [Tooltip("反応時間を画面上に表示する")]
    public bool showReactionTimeUI = true;
    [Tooltip("反応時間表示用のUI Text（任意）。未設定なら表示は行いません")]
    public Text reactionTimeText;

    [Header("Experiment Settings")]
    [Tooltip("被験者ID。ファイル名とCSV内に記録されます。")]
    public string subjectID = "sample";

    [Tooltip("最大試行回数。これに達すると実験終了。左右均等モード時は偶数にしてください。")]
    public int maxTrials = 30;

    [Tooltip("有効にすると左右が同じ回数ずつランダムな順序で出現します。")]
    public bool balanceLeftRight = true;
    
    [Tooltip("マウス感度。HorizontalLookスクリプトに反映されます。")]
    public float mouseSensitivity = 200.0f;
    
    [Tooltip("反応とみなす角度(度)")]
    public float angleThreshold = 15.0f;
    [Tooltip("中央とみなす角度(度)")]
    public float centerThreshold = 2.0f;
    
    public float minWaitTime = 2.0f; // 試行間の待機時間(最小)
    public float maxWaitTime = 4.0f; // 試行間の待機時間(最大)

    // --- 内部変数 ---
    private SerialPort _serialPort;
    private State _currentState = State.Idle;
    private Stopwatch _reactionStopwatch = new Stopwatch(); // 高精度タイマー
    private string _currentTargetDirection = ""; 
    
    // CSV記録用
    private string _csvFilePath;
    private StreamWriter _csvWriter;
    private int _trialCount = 0;

    // 左右別の反応時間記録（平均計算用）
    private List<double> _reactionTimesLeft = new List<double>();
    private List<double> _reactionTimesRight = new List<double>();

    // シリアル通信キュー (非同期送信)
    private ConcurrentQueue<string> _serialQueue = new ConcurrentQueue<string>();
    private Thread _serialThread;
    private volatile bool _serialRunning = false;

    // パラメータ変更検知用
    private int _lastSentWidth;
    private int _lastSentCount;
    private int _lastSentBurst;
    private int _lastSentInterval;

    // UI表示切り替え検知用
    private bool _lastShowReactionTimeUI;

    // 左右均等モード用のシャッフル済みリスト
    private List<int> _trialOrder;  // 0=L, 1=R
    private int _trialIndex = 0;

    void Start()
    {
        // フレームレート制限を解除して高精度な反応時間計測を実現
        Application.targetFrameRate = 300;
        QualitySettings.vSyncCount = 0;

        ApplySensitivity(); // 感度設定の適用
        SetupSerial();      // Arduino接続
        SetupCSV();         // ログファイル作成
        GenerateTrialOrder(); // 試行順序生成
        
        SendEMSConfig();    // 初期のEMS設定を送信

        // オブジェクト初期化
        targetLeft.SetActive(false);
        targetRight.SetActive(false);
        targetCenter.SetActive(false);

        // 反応時間UI初期化
        _lastShowReactionTimeUI = showReactionTimeUI;
        ApplyReactionTimeUIVisibility();
        ClearReactionTimeUI();

        // 実験開始（まずは中央を向くところから）
        StartCenterCheck();
    }

    void Update()
    {
        // 1. テストトリガーの監視
        HandleTestTriggers();
        
        // 2. 設定変更の監視（インスペクタで数値を変えたら即送信）
        if (_lastSentWidth != emsPulseWidth || 
            _lastSentCount != emsPulseCount || 
            _lastSentBurst != emsBurstCount ||
            _lastSentInterval != emsPulseInterval)
        {
            SendEMSConfig();
        }

        // 2.5. UI表示設定の監視（インスペクタで切り替えたら即反映）
        if (_lastShowReactionTimeUI != showReactionTimeUI)
        {
            _lastShowReactionTimeUI = showReactionTimeUI;
            ApplyReactionTimeUIVisibility();
        }

        // 3. クロスヘアの色更新
        UpdateCrosshair();

        // 4. メインステートマシン
        switch (_currentState)
        {
            case State.ReturnToCenter:
                CheckCenterAlignment();
                break;
            case State.Measuring:
                CheckReaction();
                break;
        }
    }

    // --- EMS制御 ---
    void SendEMSConfig()
    {
        _serialQueue.Enqueue($"W{emsPulseWidth}");
        _serialQueue.Enqueue($"C{emsPulseCount}");
        _serialQueue.Enqueue($"B{emsBurstCount}");
        _serialQueue.Enqueue($"I{emsPulseInterval}");
        _lastSentWidth = emsPulseWidth;
        _lastSentCount = emsPulseCount;
        _lastSentBurst = emsBurstCount;
        _lastSentInterval = emsPulseInterval;
    }

    void HandleTestTriggers()
    {
        if (testTriggerLeft) 
        { 
            SendSignal("L"); 
            testTriggerLeft = false; 
            UnityEngine.Debug.Log("Test Trigger: Left"); 
        }
        if (testTriggerRight) 
        { 
            SendSignal("R"); 
            testTriggerRight = false; 
            UnityEngine.Debug.Log("Test Trigger: Right"); 
        }
    }

    void SendSignal(string dir)
    {
        if (!emsEnabled) return;
        _serialQueue.Enqueue(dir);
    }

    // --- 実験フロー制御 ---

    /// <summary>
    /// 左右均等モード時、L(0)とR(1)を半数ずつ含むリストをシャッフルして生成する。
    /// maxTrialsが奇数の場合は切り上げて1回多い方をランダムに決める。
    /// </summary>
    void GenerateTrialOrder()
    {
        _trialOrder = new List<int>();
        _trialIndex = 0;

        if (!balanceLeftRight) return;

        int halfL = maxTrials / 2;
        int halfR = maxTrials / 2;
        if (maxTrials % 2 != 0)
        {
            // 奇数の場合、どちらに1回多く割り当てるかランダム
            if (UnityEngine.Random.Range(0, 2) == 0) halfL++; else halfR++;
        }

        for (int i = 0; i < halfL; i++) _trialOrder.Add(0); // L
        for (int i = 0; i < halfR; i++) _trialOrder.Add(1); // R

        // Fisher-Yates シャッフル
        for (int i = _trialOrder.Count - 1; i > 0; i--)
        {
            int j = UnityEngine.Random.Range(0, i + 1);
            int tmp = _trialOrder[i];
            _trialOrder[i] = _trialOrder[j];
            _trialOrder[j] = tmp;
        }
    }

    void ApplySensitivity()
    {
        var lookScript = playerCamera.GetComponent<HorizontalLook>();
        if (lookScript != null)
        {
            lookScript.mouseSensitivity = mouseSensitivity;
        }
        else
        {
            UnityEngine.Debug.LogError("Main Cameraに 'HorizontalLook' がアタッチされていません！");
        }
    }

    void StartCenterCheck()
    {
        targetCenter.SetActive(true);
        _currentState = State.ReturnToCenter;
    }

    void CheckCenterAlignment()
    {
        float currentY = playerBody.eulerAngles.y;
        
        // 角度がほぼ0度（正面）なら次へ
        if (Mathf.Abs(Mathf.DeltaAngle(0, currentY)) < centerThreshold)
        {
            _currentState = State.WaitRandom; // 先に状態を変えて多重起動を防ぐ
            StartCoroutine(WaitRoutine());
        }
    }

    IEnumerator WaitRoutine()
    {
        // ランダムな時間待機
        float waitTime = UnityEngine.Random.Range(minWaitTime, maxWaitTime);
        yield return new WaitForSeconds(waitTime);
        
        // 試行開始
        StartCoroutine(ExecuteTrialSequence());
    }

    IEnumerator ExecuteTrialSequence()
    {
        // 方向決定
        int direction;
        if (balanceLeftRight && _trialIndex < _trialOrder.Count)
        {
            direction = _trialOrder[_trialIndex];
            _trialIndex++;
        }
        else
        {
            direction = UnityEngine.Random.Range(0, 2);
        }
        GameObject targetObj = (direction == 0) ? targetLeft : targetRight;
        string dirStr = (direction == 0) ? "L" : "R";
        _currentTargetDirection = dirStr;

        // 左右に応じた遅延時間を選択
        float offset = (dirStr == "L") ? stimulusTimingOffsetLeft : stimulusTimingOffsetRight;

        // タイミング制御
        if (offset < 0) 
        {
            // パターンA: 先行刺激 (Agency-EMSなど)
            SendSignal(dirStr);
            yield return new WaitForSeconds(Mathf.Abs(offset));
            ShowVisualTarget(targetObj);
        }
        else 
        {
            // パターンB: 同時または遅延刺激
            ShowVisualTarget(targetObj);
            
            if (offset > 0)
            {
                yield return new WaitForSeconds(offset);
                SendSignal(dirStr);
            }
            else
            {
                // オフセット0なら即時
                SendSignal(dirStr);
            }
        }
    }

    void ShowVisualTarget(GameObject targetObj)
    {
        targetCenter.SetActive(false); // 中央を消す
        targetObj.SetActive(true);     // ターゲット表示

        ClearReactionTimeUI();
        
        _reactionStopwatch.Restart();  // 高精度タイマー開始
        _currentState = State.Measuring;
    }

    void CheckReaction()
    {
        float currentY = playerBody.eulerAngles.y;
        float angleDiff = Mathf.DeltaAngle(0, currentY); // 正面からの角度差
        bool reactionDetected = false;

        // 左ターゲットならマイナス回転、右ならプラス回転で判定
        if (_currentTargetDirection == "L" && angleDiff < -angleThreshold) reactionDetected = true;
        else if (_currentTargetDirection == "R" && angleDiff > angleThreshold) reactionDetected = true;

        if (reactionDetected)
        {
            _reactionStopwatch.Stop();
            double reactionTime = _reactionStopwatch.Elapsed.TotalMilliseconds;
            UnityEngine.Debug.Log($"<color=cyan>反応時間 ({_currentTargetDirection}): {reactionTime:F2} ms</color>");

            SetReactionTimeUI(reactionTime, _currentTargetDirection);
            
            // データを記録
            RecordData(reactionTime);

            // ターゲットを消す
            targetLeft.SetActive(false);
            targetRight.SetActive(false);

            // 終了判定
            if (_trialCount >= maxTrials)
            {
                EndExperiment();
            }
            else
            {
                StartCenterCheck(); // 次の試行へ
            }
        }
    }

    // --- データ記録 (CSV) ---
    void SetupCSV()
    {
        string directoryPath = Application.dataPath + "/../ExperimentData";
        if (!Directory.Exists(directoryPath))
        {
            Directory.CreateDirectory(directoryPath);
        }
        
        string emsTag = emsEnabled ? "EMS_ON" : "EMS_OFF";
        string fileName = $"Data_{subjectID}_{emsTag}_{DateTime.Now:yyyyMMdd_HHmmss}.csv";
        _csvFilePath = Path.Combine(directoryPath, fileName);

        // StreamWriterを保持して効率的に書き込み
        _csvWriter = new StreamWriter(_csvFilePath, false, System.Text.Encoding.UTF8);
        _csvWriter.AutoFlush = true; // 各書き込み後に自動フラッシュ（データ損失防止）

        // 固定パラメータをヘッダブロックとして記録
        _csvWriter.WriteLine("--- Settings ---");
        _csvWriter.WriteLine($"Subject ID,{subjectID}");
        _csvWriter.WriteLine($"Date,{DateTime.Now:yyyy-MM-dd HH:mm:ss}");
        _csvWriter.WriteLine($"EMS Enabled,{emsEnabled}");
        _csvWriter.WriteLine($"Sensitivity,{mouseSensitivity}");
        _csvWriter.WriteLine($"AngleThreshold(deg),{angleThreshold}");
        _csvWriter.WriteLine($"CenterThreshold(deg),{centerThreshold}");
        _csvWriter.WriteLine($"WaitTime(s),{minWaitTime}-{maxWaitTime}");
        _csvWriter.WriteLine($"PulseWidth(us),{emsPulseWidth}");
        _csvWriter.WriteLine($"PulseCount,{emsPulseCount}");
        _csvWriter.WriteLine($"BurstCount,{emsBurstCount}");
        _csvWriter.WriteLine($"PulseInterval(us),{emsPulseInterval}");
        _csvWriter.WriteLine($"StimulusOffsetL(s),{stimulusTimingOffsetLeft}");
        _csvWriter.WriteLine($"StimulusOffsetR(s),{stimulusTimingOffsetRight}");
        _csvWriter.WriteLine($"MaxTrials,{maxTrials}");
        _csvWriter.WriteLine();

        // 試行データのヘッダー（変動値のみ）
        _csvWriter.WriteLine("Trial,Direction,ReactionTime(ms),Timestamp");
        
        UnityEngine.Debug.Log($"データ保存先: {_csvFilePath}");
    }

    void RecordData(double reactionTime)
    {
        _trialCount++;
        string timeStamp = DateTime.Now.ToString("HH:mm:ss.fff");

        // 左右別にリストに記録
        if (_currentTargetDirection == "L")
            _reactionTimesLeft.Add(reactionTime);
        else
            _reactionTimesRight.Add(reactionTime);
        
        // CSVに1行追記（変動値のみ）
        _csvWriter.WriteLine($"{_trialCount},{_currentTargetDirection},{reactionTime:F2},{timeStamp}");
    }

    void WriteSummaryToCSV()
    {
        _csvWriter.WriteLine();
        _csvWriter.WriteLine("--- Summary ---");

        if (_reactionTimesLeft.Count > 0)
        {
            double avgL = 0;
            foreach (double t in _reactionTimesLeft) avgL += t;
            avgL /= _reactionTimesLeft.Count;
            _csvWriter.WriteLine($"Left(L) Avg,{avgL:F2} ms,n={_reactionTimesLeft.Count}");
        }
        else
        {
            _csvWriter.WriteLine("Left(L) Avg,N/A,n=0");
        }

        if (_reactionTimesRight.Count > 0)
        {
            double avgR = 0;
            foreach (double t in _reactionTimesRight) avgR += t;
            avgR /= _reactionTimesRight.Count;
            _csvWriter.WriteLine($"Right(R) Avg,{avgR:F2} ms,n={_reactionTimesRight.Count}");
        }
        else
        {
            _csvWriter.WriteLine("Right(R) Avg,N/A,n=0");
        }

        int totalCount = _reactionTimesLeft.Count + _reactionTimesRight.Count;
        if (totalCount > 0)
        {
            double totalSum = 0;
            foreach (double t in _reactionTimesLeft) totalSum += t;
            foreach (double t in _reactionTimesRight) totalSum += t;
            double avgAll = totalSum / totalCount;
            _csvWriter.WriteLine($"Overall Avg,{avgAll:F2} ms,n={totalCount}");
        }
        else
        {
            _csvWriter.WriteLine("Overall Avg,N/A,n=0");
        }
    }

    // --- その他 (UI, Serial, 終了処理) ---
    void UpdateCrosshair()
    {
        Ray ray = new Ray(playerCamera.position, playerCamera.forward);
        RaycastHit hit;
        
        if (Physics.Raycast(ray, out hit))
        {
            if (hit.collider.gameObject == targetCenter)
            {
                crosshairImage.color = crosshairActiveColor;
                return;
            }
        }
        crosshairImage.color = crosshairNormalColor;
    }

    void ApplyReactionTimeUIVisibility()
    {
        if (reactionTimeText == null) return;
        reactionTimeText.gameObject.SetActive(showReactionTimeUI);

        if (!showReactionTimeUI)
        {
            reactionTimeText.text = "";
        }
    }

    void ClearReactionTimeUI()
    {
        if (!showReactionTimeUI) return;
        if (reactionTimeText == null) return;
        reactionTimeText.text = "";
    }

    void SetReactionTimeUI(double reactionTimeMs, string dir)
    {
        if (!showReactionTimeUI) return;
        if (reactionTimeText == null) return;
        reactionTimeText.text = $"RT ({dir}): {reactionTimeMs:F2} ms";
    }

    void EndExperiment()
    {
        UnityEngine.Debug.Log("規定回数に達しました。実験を終了します。");
        WriteSummaryToCSV();
        CleanupResources();

        #if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;
        #else
            Application.Quit();
        #endif
    }

    void SetupSerial()
    {
        try {
            _serialPort = new SerialPort(portName, baudRate);
            _serialPort.Open();
            _serialPort.ReadTimeout = 50;
            UnityEngine.Debug.Log($"シリアルポート {portName} 接続成功");

            // バックグラウンドスレッドでシリアル送信を処理
            _serialRunning = true;
            _serialThread = new Thread(SerialWorker);
            _serialThread.IsBackground = true;
            _serialThread.Start();
        } catch (Exception e) {
            UnityEngine.Debug.LogWarning("Arduino未接続 (シミュレーションモード): " + e.Message);
        }
    }

    /// <summary>
    /// バックグラウンドスレッドでキューからメッセージを取り出し送信する
    /// </summary>
    void SerialWorker()
    {
        while (_serialRunning)
        {
            if (_serialQueue.TryDequeue(out string message))
            {
                try
                {
                    if (_serialPort != null && _serialPort.IsOpen)
                    {
                        _serialPort.WriteLine(message);
                    }
                }
                catch (Exception e)
                {
                    UnityEngine.Debug.LogWarning($"シリアル送信エラー: {e.Message}");
                }
            }
            else
            {
                Thread.Sleep(1); // キューが空なら1msスリープしてCPU負荷を抑える
            }
        }
    }

    void CleanupResources()
    {
        // シリアルスレッド停止
        _serialRunning = false;
        if (_serialThread != null && _serialThread.IsAlive)
        {
            _serialThread.Join(500); // 最大500ms待機
        }

        // シリアルポートを閉じる
        if (_serialPort != null && _serialPort.IsOpen) _serialPort.Close();

        // CSVライターを閉じる
        if (_csvWriter != null)
        {
            _csvWriter.Close();
            _csvWriter = null;
        }
    }

    void OnApplicationQuit()
    {
        CleanupResources();
    }
}