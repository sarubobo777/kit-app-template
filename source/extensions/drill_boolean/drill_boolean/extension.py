# 必要なライブラリをインポートします
import omni.ext
import omni.kit.app
import omni.usd
import numpy as np
import trimesh
import carb
from pxr import Usd, UsdGeom, Gf, Sdf, Vt

# ログ出力用の共通プレフィックスです
LOG_PREFIX = "[my_extension][Doril_boolean]"

class DorilBooleanExtension(omni.ext.IExt):
    """
    ドリルオブジェクトが金属オブジェクトに接触した際に、
    リアルタイムでブーリアン差分演算を行い、金属を削る拡張機能です。
    """
    def on_startup(self, ext_id: str) -> None:
        """拡張機能の起動時に呼び出される初期化処理です。"""
        print(f"{LOG_PREFIX} Doril_boolean extension starting up.")

        # 処理対象となるオブジェクトのパスを定義します
        self._drill_path = "/World/Drill"
        self._metal_path = "/World/Metal"

        # 毎フレームの更新イベントを購読（サブスクライブ）し、_on_update関数を呼び出すように設定します
        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="realtime_boolean_update"
        )

        # ドリルの最後のトランスフォーム（位置・回転・スケール）を保存しておく変数です
        self._last_drill_transform = None
        # ブーリアン演算の処理中に、重複して処理が走らないようにするためのフラグです
        self._is_processing = False

        print(f"{LOG_PREFIX} Ready to process boolean operations.")
        print(f"{LOG_PREFIX} Ensure a 'Drill' prim exists at '{self._drill_path}' and a 'Metal' prim at '{self._metal_path}'.")

    def on_shutdown(self) -> None:
        """拡張機能の終了時に呼び出されるクリーンアップ処理です。"""
        print(f"{LOG_PREFIX} Doril_boolean extension shutting down.")
        # 更新イベントの購読を解除します
        if self._update_sub:
            self._update_sub.unsubscribe()
            self._update_sub = None

    def _get_prim_mesh(self, prim: Usd.Prim) -> trimesh.Trimesh | None:
        """
        USDプリムからワールド座標系に変換されたtrimeshメッシュを生成します。
        UsdGeom.Meshでないプリミティブ（Cubeなど）の場合は、バウンディングボックスからメッシュを生成します。
        """
        if not prim or not prim.IsValid():
            return None

        # ワールド座標への変換行列を取得します
        xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        world_transform = xform_cache.GetLocalToWorldTransform(prim)

        # プリムがUsdGeom.Meshであるか試みます
        mesh_geom = UsdGeom.Mesh(prim)
        points_attr = mesh_geom.GetPointsAttr().Get()
        indices_attr = mesh_geom.GetFaceVertexIndicesAttr().Get()
        counts_attr = mesh_geom.GetFaceVertexCountsAttr().Get()

        if not points_attr or not indices_attr or not counts_attr:
            # メッシュデータがない場合、バウンディングボックスから立方体メッシュを生成します
            print(f"{LOG_PREFIX} Prim at {prim.GetPath()} is not a mesh. Using its bounding box as a fallback.")
            boundable = UsdGeom.Boundable(prim)
            bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
            bbox = bbox_cache.ComputeWorldBound(prim)
            if bbox.IsEmpty():
                print(f"{LOG_PREFIX} Could not compute bounding box for {prim.GetPath()}.")
                return None

            box_range = bbox.GetRange()
            extents = box_range.GetSize()

            # バウンディングボックスは既にワールド座標なので、変換済みのメッシュを作成します
            mesh = trimesh.creation.box(extents=extents, transform=np.array(world_transform))
            mesh.show()
        else:
            # メッシュデータがある場合、trimeshオブジェクトを生成します
            faces = []
            current_index = 0
            for count in counts_attr:
                # trimeshが三角形メッシュを基本とするため、ポリゴンを三角形に分割（ファン分割）します
                face_indices = indices_attr[current_index : current_index + count]
                for i in range(1, count - 1):
                    faces.append([face_indices[0], face_indices[i], face_indices[i+1]])
                current_index += count

            mesh = trimesh.Trimesh(vertices=np.array(points_attr), faces=faces)
            # ローカル座標のメッシュをワールド座標に変換します
            mesh.apply_transform(np.array(world_transform))
            mesh.show()

        # watertight（水漏れしない、閉じたメッシュ）でない場合、ブーリアン演算が失敗することがあるため修復を試みます
        if not mesh.is_watertight:
            print(f"{LOG_PREFIX} Warning: Mesh at {prim.GetPath()} is not watertight. Attempting to fill holes.")
            mesh.fill_holes()
            mesh.show()

        return mesh

    def _update_metal_mesh(self, stage: Usd.Stage, result_mesh: trimesh.Trimesh) -> None:
        """金属オブジェクトのメッシュを、ブーリアン演算結果のtrimeshデータで更新します。"""
        metal_prim = stage.GetPrimAtPath(self._metal_path)
        if not metal_prim.IsValid():
            print(f"{LOG_PREFIX} Metal prim at {self._metal_path} is not valid for updating.")
            return

        # 結果メッシュはワールド座標なので、金属プリムのローカル座標に戻します
        xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        world_to_local_transform = xform_cache.GetLocalToWorldTransform(metal_prim).GetInverse()

        # 頂点データをローカル座標に変換します
        local_vertices = trimesh.transform_points(result_mesh.vertices, np.array(world_to_local_transform))

        usd_mesh = UsdGeom.Mesh(metal_prim)

        # USDのメッシュ属性を新しいデータで更新します
        usd_mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(local_vertices))
        # trimeshの面は常に三角形なので、頂点数は3で固定です
        usd_mesh.GetFaceVertexCountsAttr().Set([3] * len(result_mesh.faces))
        usd_mesh.GetFaceVertexIndicesAttr().Set(result_mesh.faces.flatten().astype(int).tolist())

        print(f"{LOG_PREFIX} Metal mesh updated successfully.")

    def _perform_boolean_operation(self) -> None:
        """ブーリアン差分演算を実行し、メッシュを更新するメインの関数です。"""
        self._is_processing = True # 処理中フラグをON
        print(f"{LOG_PREFIX} Starting boolean operation...")

        stage = omni.usd.get_context().get_stage()
        if not stage:
            self._is_processing = False
            return

        drill_prim = stage.GetPrimAtPath(self._drill_path)
        metal_prim = stage.GetPrimAtPath(self._metal_path)

        # プリムからtrimeshオブジェクトを取得します
        metal_mesh = self._get_prim_mesh(metal_prim)
        drill_mesh = self._get_prim_mesh(drill_prim)

        if metal_mesh is None or drill_mesh is None:
            print(f"{LOG_PREFIX} Failed to create one or both trimesh objects.")
            self._is_processing = False
            return

        # watertightでないメッシュではブーリアン演算が失敗するため、処理を中断します
        if not metal_mesh.is_watertight or not drill_mesh.is_watertight:
            print(f"{LOG_PREFIX} Error: One or both meshes are not watertight, cannot perform boolean operation.")
            print(f"{LOG_PREFIX} -> Metal watertight: {metal_mesh.is_watertight}, Drill watertight: {drill_mesh.is_watertight}")
            self._is_processing = False
            return

        # ブーリアン差分演算を実行します (engine='blender'は安定性が高いです)
        try:
            result_mesh = trimesh.boolean.difference([metal_mesh, drill_mesh], engine='blender')
        except Exception as e:
            print(f"{LOG_PREFIX} Trimesh boolean operation failed: {e}")
            self._is_processing = False
            return

        if result_mesh.is_empty:
            print(f"{LOG_PREFIX} Boolean operation resulted in an empty mesh. Hiding the metal prim.")
            # 削りきってメッシュが空になった場合、金属プリムを非表示にします
            UsdGeom.Imageable(metal_prim).MakeInvisible()
        else:
            # 演算結果でメッシュを更新します
            self._update_metal_mesh(stage, result_mesh)

        print(f"{LOG_PREFIX} Boolean operation finished.")
        self._is_processing = False # 処理中フラグをOFF

    def _on_update(self, e: carb.events.IEvent) -> None:
        """毎フレーム呼び出され、接触判定と処理のトリガーとなります。"""
        # 前の処理が実行中の場合は、このフレームでは何もしません
        if self._is_processing:
            return

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        drill_prim = stage.GetPrimAtPath(self._drill_path)
        metal_prim = stage.GetPrimAtPath(self._metal_path)

        # プリムが存在し、かつ金属が表示されているか確認します
        if not drill_prim.IsValid() or not metal_prim.IsValid() or UsdGeom.Imageable(metal_prim).ComputeVisibility() == UsdGeom.Tokens.invisible:
            return

        # ドリルの現在のワールド座標変換行列を取得します
        xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        current_drill_transform = xform_cache.GetLocalToWorldTransform(drill_prim)

        # ドリルが前回から動いていない場合は、無駄な処理を省きます
        if self._last_drill_transform is not None and current_drill_transform == self._last_drill_transform:
            return

        # ドリルの位置が更新されたので、衝突判定を行います
        self._last_drill_transform = current_drill_transform

        # 高速なバウンディングボックスでの衝突判定を行います
        #boundable_drill = UsdGeom.Boundable(drill_prim)
        #boundable_metal = UsdGeom.Boundable(metal_prim)
        bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])

        drill_bbox = bbox_cache.ComputeWorldBound(drill_prim).GetBox()
        metal_bbox = bbox_cache.ComputeWorldBound(metal_prim).GetBox()

        self._perform_boolean_operation()

        # バウンディングボックスが交差している場合のみ、重いブーリアン処理に進みます
        #if drill_bbox.IntersectWith(metal_bbox):
            # 衝突を検知したら、ブーリアン演算を実行します
            #self._perform_boolean_operation()