groovy
pipeline {
    agent any

    parameters {
        text(name: 'MANUAL_TEST_LIST', defaultValue: '', description: '手动触发时输入测试列表 (格式: test_name,seed)，若为空则读取 testlist.csv')
    }

    triggers {
        // 当 main 分支有 push 时触发
        pollSCM('H/5 * * * *') 
    }

    environment {
        EMAIL_RECIPIENTS = "verification_team@example.com"
        COVERAGE_DIR = "coverage_results"
    }

    stages {
        stage('Prepare') {
            steps {
                script {
                    // 清理旧结果目录
                    sh "rm -rf results.json results_dir && mkdir results_dir"
                    sh "rm -rf ${COVERAGE_DIR} && mkdir ${COVERAGE_DIR}"
                    
                    // 确定测试列表来源
                    def csvContent = ""
                    if (params.MANUAL_TEST_LIST && params.MANUAL_TEST_LIST.trim() != "") {
                        csvContent = params.MANUAL_TEST_LIST.trim()
                        echo "使用手动输入的测试列表"
                    } else {
                        csvContent = readFile('testlist.csv').trim()
                        echo "读取 testlist.csv 文件"
                    }
                    
                    // 解析测试用例
                    env.TEST_CASES = csvContent
                }
            }
        }

        stage('Parallel Simulation') {
            steps {
                script {
                    def lines = env.TEST_CASES.split('\n')
                    def tasks = [:]

                    lines.each { line ->
                        def parts = line.split(',')
                        if (parts.size() == 2) {
                            def testName = parts[0].trim()
                            def seed = parts[1].trim()

                            tasks[testName] = {
                                node(NODE_NAME) { // 在当前节点或指定节点执行
                                    stage("Test: ${testName}") {
                                        def status = "PASS"
                                        def startTime = System.currentTimeMillis()
                                        
                                        try {
                                            timeout(time: 30, unit: 'MINUTES') {
                                                // 1. 执行仿真 (假设 vcs 编译已完成，此处执行 simv)
                                                // +ntb_random_seed 指定种子, -cm 指定覆盖率输出
                                                sh """
                                                   ./simv +ntb_random_seed=${seed} \
                                                          +UVM_TESTNAME=${testName} \
                                                          -cm line+cond+fsm+tgl -cm_name ${testName} \
                                                          -l ${testName}.log || true
                                                """
                                            }

                                            // 2. 结果解析
                                            def logContent = readFile("${testName}.log")
                                            if (logContent.contains("UVM_ERROR") || logContent.contains("UVM_FATAL") || logContent.contains("FATAL")) {
                                                status = "FAIL"
                                                currentBuild.result = 'UNSTABLE'
                                            }
                                        } catch (hub.jenkins.plugins.terminate.TerminateException e) {
                                            status = "TIMEOUT"
                                            currentBuild.result = 'UNSTABLE'
                                        } catch (Exception e) {
                                            status = "ERROR"
                                            currentBuild.result = 'UNSTABLE'
                                        } finally {
                                            def duration = (System.currentTimeMillis() - startTime) / 1000
                                            // 将结果写入临时 JSON 文件防止并发写冲突
                                            def resultJson = "{\"test_name\": \"${testName}\", \"seed\": \"${seed}\", \"result\": \"${status}\", \"duration\": \"${duration}s\"}"
                                            writeFile file: "results_dir/${testName}.json", text: resultJson
                                            
                                            // 收集覆盖率文件 (vdb)
                                            sh "cp -r simv.vdb ${COVERAGE_DIR}/${testName}.vdb || true"
                                        }
                                    }
                                }
                            }
                        }
                    }
                    parallel tasks
                }
            }
        }

        stage('Post-Process') {
            steps {
                script {
                    // 1. 合并结果 JSON
                    sh "echo '[' > results.json"
                    sh "cat results_dir/*.json | sed 's/}/},/g' | sed '\$ s/,\$//' >> results.json"
                    sh "echo ']' >> results.json"

                    // 2. 合并覆盖率并生成报告
                    // 假设 merge_coverage.py 会调用 urg 工具
                    sh "python3 merge_coverage.py --dir ${COVERAGE_DIR} --output merged_vdb"
                    sh "urg -dir merged_vdb.vdb -format html -report html_report"
                }
            }
        }
    }

    post {
        always {
            // 归档产物
            archiveArtifacts artifacts: 'html_report/**, results.json, *.log', followSymlinks: false
            
            script {
                // 读取结果用于邮件
                def results = readJSON file: 'results.json'
                def tableRows = ""
                results.each { res ->
                    def color = res.result == 'PASS' ? 'green' : 'red'
                    tableRows += """
                        <tr>
                            <td>${res.test_name}</td>
                            <td>${res.seed}</td>
                            <td style="color: ${color}">${res.result}</td>
                            <td>${res.duration}</td>
                        </tr>
                    """
                }

                def emailBody = """
                    <h3>Simulation Summary Report</h3>
                    <table border="1" style="border-collapse: collapse;">
                        <tr style="background-color: #f2f2f2;">
                            <th>Test Name</th><th>Seed</th><th>Result</th><th>Duration</th>
                        </tr>
                        ${tableRows}
                    </table>
                    <p><b>Coverage Report:</b> <a href="${env.BUILD_URL}artifact/html_report/dashboard.html">View HTML Report</a></p>
                    <p>Job URL: ${env.BUILD_URL}</p>
                """

                emailext (
                    subject: "Regression Result: ${currentBuild.fullDisplayName} - ${currentBuild.result}",
                    body: emailBody,
                    to: "${EMAIL_RECIPIENTS}",
                    mimeType: 'text/html'
                )
            }
        }
    }
}