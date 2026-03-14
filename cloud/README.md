# Cloud MATSim Execution

大規模MATSimシミュレーションをAWSで実行する手順。

## 推奨インスタンス

| エージェント数 | インスタンス | RAM | 費用/時間 | 実行時間 |
|---|---|---|---|---|
| 10万 | r6g.2xlarge | 64 GB | ~$0.50 | ~15分 |
| 50万 | r6g.4xlarge | 128 GB | ~$1.00 | ~1時間 |
| 100万 | r6g.8xlarge | 256 GB | ~$2.00 | ~3時間 |

※ Graviton (ARM) インスタンスが最もコスパ良い

## 手順

### 1. EC2起動
```bash
aws ec2 run-instances \
  --image-id ami-0abcdef1234567890 \
  --instance-type r6g.4xlarge \
  --key-name your-key \
  --security-group-ids sg-xxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=matsim-run}]'
```

### 2. コード転送
```bash
rsync -avz --exclude='data/output' --exclude='.venv' --exclude='cache' \
  ./ ec2-user@<instance-ip>:~/ajtg/
```

### 3. 実行
```bash
ssh ec2-user@<instance-ip>
cd ~/ajtg
AGENTS=500000 ITERATIONS=10 bash cloud/run_matsim_cloud.sh
```

### 4. 結果回収
```bash
scp -r ec2-user@<instance-ip>:~/ajtg/data/output/matsim_cloud/viz/ ./web/data/
```

### 5. インスタンス停止
```bash
aws ec2 stop-instances --instance-ids <instance-id>
```

## サンプリングについて

MATSim の `flowCapacityFactor` でサンプリング率を設定：
- 50万エージェント × factor=0.01 → 統計的に5000万人相当
- ただし「代表点」ではない。ルート多様性が不十分

より正確にするには：
- エージェント数を増やす（100万以上）
- イテレーション数を増やす（20-50）
- パーソントリップ調査データからODマトリクスを構築
