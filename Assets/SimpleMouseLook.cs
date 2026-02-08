using UnityEngine;

public class SimpleMouseLook : MonoBehaviour
{
    public float mouseSensitivity = 100f; // マウス感度
    float xRotation = 0f;

    void Start()
    {
        // マウスカーソルを画面中央にロックして消す
        Cursor.lockState = CursorLockMode.Locked;
    }

    void Update()
    {
        // マウスの動きを取得
        float mouseX = Input.GetAxis("Mouse X") * mouseSensitivity * Time.deltaTime;
        float mouseY = Input.GetAxis("Mouse Y") * mouseSensitivity * Time.deltaTime;

        // 上下の視点移動（首を縦に振る）
        xRotation -= mouseY;
        xRotation = Mathf.Clamp(xRotation, -90f, 90f); // 真上・真下で止める

        // カメラ自体を上下回転
        transform.localRotation = Quaternion.Euler(xRotation, 0f, 0f);
        
        // プレイヤーの体（親オブジェクト）を左右回転
        // ここが重要：左右の回転は親オブジェクト(Player)を回す
        if(transform.parent != null)
        {
            transform.parent.Rotate(Vector3.up * mouseX);
        }
    }
}